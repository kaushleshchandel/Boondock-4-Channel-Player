"""Database models for audio streams."""
import sqlite3
import os
from config import Config

def get_db():
    conn = sqlite3.connect(Config.DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS audio_streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS audio_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stream_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            order_index INTEGER DEFAULT 0,
            FOREIGN KEY (stream_id) REFERENCES audio_streams(id) ON DELETE CASCADE
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS noise_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            filename TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS device_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            mac TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS firmwares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            firmware_filename TEXT,
            bootloader_filename TEXT,
            partition_filename TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Check if output_channels table needs migration
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='output_channels'")
    if cursor.fetchone():
        cursor = conn.execute("PRAGMA table_info(output_channels)")
        columns = [row[1] for row in cursor.fetchall()]
        if 'channel' in columns or 'volume' not in columns or 'noise_preset' not in columns or 'file_delay' not in columns or 'is_playing' not in columns:
            # Need to migrate - save data, drop, recreate
            old_data = conn.execute('SELECT id, name, device_id, stream_id FROM output_channels').fetchall()
            conn.execute('DROP TABLE output_channels')
            conn.execute('''
                CREATE TABLE output_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    device_id INTEGER NOT NULL,
                    stream_id INTEGER DEFAULT NULL,
                    volume REAL DEFAULT 1.0,
                    noise_enabled INTEGER DEFAULT 0,
                    noise_profile_id INTEGER DEFAULT NULL,
                    noise_preset TEXT DEFAULT NULL,
                    noise_volume REAL DEFAULT 0.3,
                    file_delay INTEGER DEFAULT 0,
                    noise_during_delay INTEGER DEFAULT 0,
                    is_playing INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (stream_id) REFERENCES audio_streams(id) ON DELETE SET NULL,
                    FOREIGN KEY (noise_profile_id) REFERENCES noise_profiles(id) ON DELETE SET NULL
                )
            ''')
            # Restore data
            for row in old_data:
                conn.execute(
                    'INSERT INTO output_channels (id, name, device_id, stream_id) VALUES (?, ?, ?, ?)',
                    (row[0], row[1], row[2], row[3])
                )
    else:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS output_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                device_id INTEGER NOT NULL,
                stream_id INTEGER DEFAULT NULL,
                volume REAL DEFAULT 1.0,
                noise_enabled INTEGER DEFAULT 0,
                noise_profile_id INTEGER DEFAULT NULL,
                noise_preset TEXT DEFAULT NULL,
                noise_volume REAL DEFAULT 0.3,
                file_delay INTEGER DEFAULT 0,
                noise_during_delay INTEGER DEFAULT 0,
                is_playing INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (stream_id) REFERENCES audio_streams(id) ON DELETE SET NULL,
                FOREIGN KEY (noise_profile_id) REFERENCES noise_profiles(id) ON DELETE SET NULL
            )
        ''')
    
    conn.commit()
    conn.close()
    
    # Create noise profiles folder
    os.makedirs(Config.NOISE_FOLDER, exist_ok=True)
    # Create firmwares folder
    os.makedirs(Config.FIRMWARE_FOLDER, exist_ok=True)


class NoiseProfile:
    @staticmethod
    def create(name, filename, original_filename):
        conn = get_db()
        cursor = conn.execute(
            'INSERT INTO noise_profiles (name, filename, original_filename) VALUES (?, ?, ?)',
            (name, filename, original_filename)
        )
        profile_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return profile_id
    
    @staticmethod
    def get_all():
        conn = get_db()
        profiles = conn.execute('SELECT * FROM noise_profiles ORDER BY id').fetchall()
        conn.close()
        return [dict(p) for p in profiles]
    
    @staticmethod
    def get(profile_id):
        conn = get_db()
        profile = conn.execute('SELECT * FROM noise_profiles WHERE id = ?', (profile_id,)).fetchone()
        conn.close()
        return dict(profile) if profile else None
    
    @staticmethod
    def delete(profile_id):
        conn = get_db()
        profile = conn.execute('SELECT * FROM noise_profiles WHERE id = ?', (profile_id,)).fetchone()
        if profile:
            filepath = os.path.join(Config.NOISE_FOLDER, profile['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
        conn.execute('UPDATE output_channels SET noise_profile_id = NULL, noise_enabled = 0 WHERE noise_profile_id = ?', (profile_id,))
        conn.execute('DELETE FROM noise_profiles WHERE id = ?', (profile_id,))
        conn.commit()
        conn.close()


class OutputChannel:
    @staticmethod
    def create(name, device_id):
        conn = get_db()
        cursor = conn.execute(
            'INSERT INTO output_channels (name, device_id) VALUES (?, ?)',
            (name, device_id)
        )
        channel_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return channel_id
    
    @staticmethod
    def get_all():
        conn = get_db()
        channels = conn.execute('SELECT * FROM output_channels ORDER BY id').fetchall()
        conn.close()
        return [dict(c) for c in channels]
    
    @staticmethod
    def get(channel_id):
        conn = get_db()
        channel = conn.execute('SELECT * FROM output_channels WHERE id = ?', (channel_id,)).fetchone()
        conn.close()
        return dict(channel) if channel else None
    
    @staticmethod
    def update(channel_id, name, device_id):
        conn = get_db()
        conn.execute(
            'UPDATE output_channels SET name = ?, device_id = ? WHERE id = ?',
            (name, device_id, channel_id)
        )
        conn.commit()
        conn.close()
    
    @staticmethod
    def set_stream(channel_id, stream_id):
        conn = get_db()
        conn.execute(
            'UPDATE output_channels SET stream_id = ? WHERE id = ?',
            (stream_id, channel_id)
        )
        conn.commit()
        conn.close()
    
    @staticmethod
    def set_volume(channel_id, volume):
        conn = get_db()
        conn.execute(
            'UPDATE output_channels SET volume = ? WHERE id = ?',
            (volume, channel_id)
        )
        conn.commit()
        conn.close()
    
    @staticmethod
    def set_noise(channel_id, enabled, profile_id=None, noise_volume=None, preset=None):
        conn = get_db()
        if noise_volume is not None:
            conn.execute(
                'UPDATE output_channels SET noise_enabled = ?, noise_profile_id = ?, noise_volume = ?, noise_preset = ? WHERE id = ?',
                (1 if enabled else 0, profile_id, noise_volume, preset, channel_id)
            )
        else:
            conn.execute(
                'UPDATE output_channels SET noise_enabled = ?, noise_profile_id = ?, noise_preset = ? WHERE id = ?',
                (1 if enabled else 0, profile_id, preset, channel_id)
            )
        conn.commit()
        conn.close()
    
    @staticmethod
    def set_delay(channel_id, delay, noise_during_delay):
        conn = get_db()
        conn.execute(
            'UPDATE output_channels SET file_delay = ?, noise_during_delay = ? WHERE id = ?',
            (delay, 1 if noise_during_delay else 0, channel_id)
        )
        conn.commit()
        conn.close()
    
    @staticmethod
    def set_playback_state(channel_id, is_playing):
        conn = get_db()
        conn.execute(
            'UPDATE output_channels SET is_playing = ? WHERE id = ?',
            (1 if is_playing else 0, channel_id)
        )
        conn.commit()
        conn.close()
    
    @staticmethod
    def delete(channel_id):
        conn = get_db()
        conn.execute('DELETE FROM output_channels WHERE id = ?', (channel_id,))
        conn.commit()
        conn.close()


class AudioStream:
    @staticmethod
    def create(name, description=''):
        conn = get_db()
        cursor = conn.execute(
            'INSERT INTO audio_streams (name, description) VALUES (?, ?)',
            (name, description)
        )
        stream_id = cursor.lastrowid
        conn.commit()
        conn.close()
        os.makedirs(os.path.join(Config.STREAMS_FOLDER, str(stream_id)), exist_ok=True)
        return stream_id
    
    @staticmethod
    def get_all():
        conn = get_db()
        streams = conn.execute('SELECT * FROM audio_streams ORDER BY id').fetchall()
        conn.close()
        return [dict(s) for s in streams]
    
    @staticmethod
    def get(stream_id):
        conn = get_db()
        stream = conn.execute('SELECT * FROM audio_streams WHERE id = ?', (stream_id,)).fetchone()
        conn.close()
        return dict(stream) if stream else None
    
    @staticmethod
    def delete(stream_id):
        conn = get_db()
        conn.execute('UPDATE output_channels SET stream_id = NULL WHERE stream_id = ?', (stream_id,))
        conn.execute('DELETE FROM audio_files WHERE stream_id = ?', (stream_id,))
        conn.execute('DELETE FROM audio_streams WHERE id = ?', (stream_id,))
        conn.commit()
        conn.close()
        import shutil
        stream_folder = os.path.join(Config.STREAMS_FOLDER, str(stream_id))
        if os.path.exists(stream_folder):
            shutil.rmtree(stream_folder)
    
    @staticmethod
    def update(stream_id, name, description):
        conn = get_db()
        conn.execute(
            'UPDATE audio_streams SET name = ?, description = ? WHERE id = ?',
            (name, description, stream_id)
        )
        conn.commit()
        conn.close()


class AudioFile:
    @staticmethod
    def add(stream_id, filename, original_filename):
        conn = get_db()
        max_order = conn.execute(
            'SELECT MAX(order_index) FROM audio_files WHERE stream_id = ?', (stream_id,)
        ).fetchone()[0]
        order_index = (max_order or 0) + 1
        cursor = conn.execute(
            'INSERT INTO audio_files (stream_id, filename, original_filename, order_index) VALUES (?, ?, ?, ?)',
            (stream_id, filename, original_filename, order_index)
        )
        file_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return file_id
    
    @staticmethod
    def get_by_stream(stream_id):
        conn = get_db()
        files = conn.execute(
            'SELECT * FROM audio_files WHERE stream_id = ? ORDER BY order_index',
            (stream_id,)
        ).fetchall()
        conn.close()
        return [dict(f) for f in files]
    
    @staticmethod
    def delete(file_id):
        conn = get_db()
        file = conn.execute('SELECT * FROM audio_files WHERE id = ?', (file_id,)).fetchone()
        if file:
            filepath = os.path.join(Config.STREAMS_FOLDER, str(file['stream_id']), file['filename'])
            if os.path.exists(filepath):
                os.remove(filepath)
        conn.execute('DELETE FROM audio_files WHERE id = ?', (file_id,))
        conn.commit()
        conn.close()


class DeviceAlias:
    @staticmethod
    def _normalize_mac(mac):
        """Normalize MAC address by removing colons and converting to uppercase."""
        if not mac:
            return ''
        return mac.replace(':', '').replace('-', '').upper()
    
    @staticmethod
    def get_all():
        conn = get_db()
        aliases = conn.execute('SELECT * FROM device_aliases').fetchall()
        conn.close()
        return {a['mac']: a['name'] for a in aliases}
    
    @staticmethod
    def get(mac):
        conn = get_db()
        normalized_mac = DeviceAlias._normalize_mac(mac)
        alias = conn.execute('SELECT name FROM device_aliases WHERE mac = ?', (normalized_mac,)).fetchone()
        conn.close()
        return alias['name'] if alias else None
    
    @staticmethod
    def set(mac, name):
        conn = get_db()
        normalized_mac = DeviceAlias._normalize_mac(mac)
        existing = conn.execute('SELECT id FROM device_aliases WHERE mac = ?', (normalized_mac,)).fetchone()
        if existing:
            conn.execute('UPDATE device_aliases SET name = ? WHERE mac = ?', (name, normalized_mac))
        else:
            conn.execute('INSERT INTO device_aliases (mac, name) VALUES (?, ?)', (normalized_mac, name))
        conn.commit()
        conn.close()
    
    @staticmethod
    def delete(mac):
        conn = get_db()
        normalized_mac = DeviceAlias._normalize_mac(mac)
        conn.execute('DELETE FROM device_aliases WHERE mac = ?', (normalized_mac,))
        conn.commit()
        conn.close()


class Firmware:
    @staticmethod
    def create(name, firmware_filename=None, bootloader_filename=None, partition_filename=None):
        conn = get_db()
        cursor = conn.execute(
            'INSERT INTO firmwares (name, firmware_filename, bootloader_filename, partition_filename) VALUES (?, ?, ?, ?)',
            (name, firmware_filename, bootloader_filename, partition_filename)
        )
        firmware_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return firmware_id
    
    @staticmethod
    def get_all():
        conn = get_db()
        firmwares = conn.execute('SELECT * FROM firmwares ORDER BY created_at DESC').fetchall()
        conn.close()
        return [dict(f) for f in firmwares]
    
    @staticmethod
    def get(firmware_id):
        conn = get_db()
        firmware = conn.execute('SELECT * FROM firmwares WHERE id = ?', (firmware_id,)).fetchone()
        conn.close()
        return dict(firmware) if firmware else None
    
    @staticmethod
    def delete(firmware_id):
        conn = get_db()
        firmware = conn.execute('SELECT * FROM firmwares WHERE id = ?', (firmware_id,)).fetchone()
        if firmware:
            # Delete associated files
            if firmware['firmware_filename']:
                filepath = os.path.join(Config.FIRMWARE_FOLDER, firmware['firmware_filename'])
                if os.path.exists(filepath):
                    os.remove(filepath)
            if firmware['bootloader_filename']:
                filepath = os.path.join(Config.FIRMWARE_FOLDER, firmware['bootloader_filename'])
                if os.path.exists(filepath):
                    os.remove(filepath)
            if firmware['partition_filename']:
                filepath = os.path.join(Config.FIRMWARE_FOLDER, firmware['partition_filename'])
                if os.path.exists(filepath):
                    os.remove(filepath)
        conn.execute('DELETE FROM firmwares WHERE id = ?', (firmware_id,))
        conn.commit()
        conn.close()

