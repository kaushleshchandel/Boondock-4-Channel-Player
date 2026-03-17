"""Firmware flashing service using esptool."""
import subprocess
import os
import threading
import time
import platform
import queue
from config import Config

class FirmwareService:
    def __init__(self, serial_service=None):
        self.flashing_devices = set()  # Track devices currently being flashed
        self.lock = threading.Lock()
        self.serial_service = serial_service  # Reference to serial service for disconnecting ports
        self.output_queues = {}  # port -> queue for real-time output streaming
    
    def _get_esptool_command(self):
        """Get the esptool command name for the current platform."""
        if platform.system() == 'Windows':
            # Try 'esptool' first on Windows
            return 'esptool'
        else:
            # Try 'esptool.py' first on Unix
            return 'esptool.py'
    
    def _run_esptool_streaming(self, port, command, args, output_queue):
        """
        Run esptool command and stream output line by line.
        
        Args:
            port: Serial port
            command: esptool command (e.g., ['erase-flash'])
            args: Additional arguments
            output_queue: Queue to send output lines to (line, is_stderr)
        
        Returns:
            dict with success status and returncode
        """
        esptool_cmd = self._get_esptool_command()
        cmd = [esptool_cmd, '--port', port] + command + args
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                universal_newlines=True
            )
            
            def read_output(pipe, is_stderr):
                """Read output from pipe and send to queue."""
                try:
                    for line in iter(pipe.readline, ''):
                        if line:
                            line = line.rstrip()
                            output_queue.put(('line', line, is_stderr))
                    pipe.close()
                except Exception as e:
                    output_queue.put(('error', str(e), False))
            
            # Start threads to read stdout and stderr
            stdout_thread = threading.Thread(target=read_output, args=(process.stdout, False), daemon=True)
            stderr_thread = threading.Thread(target=read_output, args=(process.stderr, True), daemon=True)
            
            stdout_thread.start()
            stderr_thread.start()
            
            # Wait for process to complete
            returncode = process.wait()
            
            # Wait for output threads to finish
            stdout_thread.join(timeout=1.0)
            stderr_thread.join(timeout=1.0)
            
            # Signal completion
            output_queue.put(('done', returncode == 0, returncode))
            
            return {
                'success': returncode == 0,
                'returncode': returncode
            }
        except FileNotFoundError:
            # Try alternative command name
            alt_cmd = 'esptool.py' if esptool_cmd == 'esptool' else 'esptool'
            cmd_alt = [alt_cmd, '--port', port] + command + args
            try:
                process = subprocess.Popen(
                    cmd_alt,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                    universal_newlines=True
                )
                
                def read_output(pipe, is_stderr):
                    try:
                        for line in iter(pipe.readline, ''):
                            if line:
                                line = line.rstrip()
                                output_queue.put(('line', line, is_stderr))
                        pipe.close()
                    except Exception as e:
                        output_queue.put(('error', str(e), False))
                
                stdout_thread = threading.Thread(target=read_output, args=(process.stdout, False), daemon=True)
                stderr_thread = threading.Thread(target=read_output, args=(process.stderr, True), daemon=True)
                
                stdout_thread.start()
                stderr_thread.start()
                
                returncode = process.wait()
                
                stdout_thread.join(timeout=1.0)
                stderr_thread.join(timeout=1.0)
                
                output_queue.put(('done', returncode == 0, returncode))
                
                return {
                    'success': returncode == 0,
                    'returncode': returncode
                }
            except FileNotFoundError:
                output_queue.put(('error', 'esptool not found. Please install esptool: pip install esptool', False))
                output_queue.put(('done', False, -1))
                return {
                    'success': False,
                    'returncode': -1
                }
        except Exception as e:
            output_queue.put(('error', str(e), False))
            output_queue.put(('done', False, -1))
            return {
                'success': False,
                'returncode': -1
            }
    
    def flash_firmware(self, port, firmware_id, firmware_path, bootloader_path=None, partition_path=None, erase_before_flash=True):
        """
        Flash firmware to ESP32 device.
        
        This method:
        1. Disconnects serial port from monitoring
        2. Optionally erases flash (if erase_before_flash is True)
        3. Writes firmware files
        4. Reconnects serial port
        
        Output is streamed via the output queue for this port.
        
        Args:
            port: Serial port (e.g., 'COM3' or '/dev/ttyUSB0')
            firmware_id: ID for tracking
            firmware_path: Path to firmware.bin
            bootloader_path: Optional path to bootloader.bin
            partition_path: Optional path to partitions.bin
            erase_before_flash: If True, run full chip erase before writing (default True)
        
        Returns:
            dict with success status
        """
        with self.lock:
            if port in self.flashing_devices:
                return {
                    'success': False,
                    'error': 'Device is already being flashed'
                }
            self.flashing_devices.add(port)
            # Create output queue for this port
            self.output_queues[port] = queue.Queue()
        
        # Disconnect serial port from monitoring service
        was_connected = False
        if self.serial_service and port in self.serial_service.connections:
            was_connected = True
            try:
                self.serial_service.disconnect(port)
                time.sleep(2.0)  # Wait for port to be fully released
            except Exception as e:
                with self.lock:
                    self.flashing_devices.discard(port)
                    if port in self.output_queues:
                        del self.output_queues[port]
                return {
                    'success': False,
                    'error': f'Failed to disconnect serial port: {str(e)}'
                }
        
        output_queue = self.output_queues.get(port)
        if not output_queue:
            with self.lock:
                self.flashing_devices.discard(port)
            return {
                'success': False,
                'error': 'Output queue not initialized'
            }
        
        try:
            # Step 1: Optionally erase flash
            if erase_before_flash:
                output_queue.put(('status', 'Erasing flash memory...', False))
                erase_result = self._run_esptool_streaming(port, ['erase-flash'], [], output_queue)
                time.sleep(0.5)
                if not erase_result['success']:
                    return {
                        'success': False,
                        'error': f'Failed to erase flash (return code: {erase_result.get("returncode", -1)})'
                    }
            
            # Step 2: Build write-flash command
            flash_args = []
            
            if bootloader_path and os.path.exists(bootloader_path):
                flash_args.extend(['0x1000', bootloader_path])
            
            if partition_path and os.path.exists(partition_path):
                flash_args.extend(['0x8000', partition_path])
            
            if firmware_path and os.path.exists(firmware_path):
                flash_args.extend(['0x10000', firmware_path])
            
            if not flash_args:
                return {
                    'success': False,
                    'error': 'No valid firmware files provided'
                }
            
            # Step 3: Write firmware
            output_queue.put(('status', 'Writing firmware to flash...', False))
            flash_result = self._run_esptool_streaming(port, ['write-flash'], flash_args, output_queue)
            
            if not flash_result['success']:
                return {
                    'success': False,
                    'error': f'Failed to write firmware (return code: {flash_result.get("returncode", -1)})'
                }
            
            output_queue.put(('status', 'Flash completed successfully!', False))
            return {
                'success': True
            }
            
        finally:
            # Reconnect serial port if it was connected before
            if was_connected and self.serial_service:
                time.sleep(1.0)  # Wait a bit before reconnecting
                try:
                    self.serial_service.connect(port)
                except Exception as e:
                    print(f'Warning: Failed to reconnect serial port {port}: {str(e)}')
            
            with self.lock:
                self.flashing_devices.discard(port)
                # Keep output queue for a bit to allow final reads, then clean up
                def cleanup_queue():
                    time.sleep(5)  # Keep queue for 5 seconds after completion
                    with self.lock:
                        if port in self.output_queues:
                            del self.output_queues[port]
                threading.Thread(target=cleanup_queue, daemon=True).start()
    
    def erase_flash(self, port):
        """
        Erase the entire flash of an ESP32 device.
        
        Args:
            port: Serial port (e.g., 'COM3' or '/dev/ttyUSB0')
        
        Returns:
            dict with success status
        """
        with self.lock:
            if port in self.flashing_devices:
                return {
                    'success': False,
                    'error': 'Device is currently being flashed'
                }
            self.flashing_devices.add(port)
            self.output_queues[port] = queue.Queue()
        
        # Disconnect serial port
        was_connected = False
        if self.serial_service and port in self.serial_service.connections:
            was_connected = True
            try:
                self.serial_service.disconnect(port)
                time.sleep(2.0)
            except Exception as e:
                with self.lock:
                    self.flashing_devices.discard(port)
                    if port in self.output_queues:
                        del self.output_queues[port]
                return {
                    'success': False,
                    'error': f'Failed to disconnect serial port: {str(e)}'
                }
        
        output_queue = self.output_queues.get(port)
        
        try:
            result = self._run_esptool_streaming(port, ['erase-flash'], [], output_queue)
            return {
                'success': result['success'],
                'error': None if result['success'] else f'Erase failed (return code: {result.get("returncode", -1)})'
            }
        finally:
            if was_connected and self.serial_service:
                time.sleep(1.0)
                try:
                    self.serial_service.connect(port)
                except Exception as e:
                    print(f'Warning: Failed to reconnect serial port {port}: {str(e)}')
            
            with self.lock:
                self.flashing_devices.discard(port)
                def cleanup_queue():
                    time.sleep(5)
                    with self.lock:
                        if port in self.output_queues:
                            del self.output_queues[port]
                threading.Thread(target=cleanup_queue, daemon=True).start()
    
    def is_flashing(self, port):
        """Check if a device is currently being flashed."""
        with self.lock:
            return port in self.flashing_devices
    
    def get_output_queue(self, port):
        """Get the output queue for a port."""
        with self.lock:
            return self.output_queues.get(port)

# Global instance - will be initialized with serial_service in app.py
firmware_service = None
