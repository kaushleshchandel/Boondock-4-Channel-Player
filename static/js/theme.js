// Theme Management
(function() {
    'use strict';
    
    // Get theme from localStorage or default to 'light'
    function getTheme() {
        return localStorage.getItem('theme') || 'light';
    }
    
    // Set theme
    function setTheme(theme) {
        if (theme === 'dark') {
            document.documentElement.setAttribute('data-theme', 'dark');
        } else {
            document.documentElement.removeAttribute('data-theme');
        }
        localStorage.setItem('theme', theme);
        updateThemeToggleIcon(theme);
    }
    
    // Update theme toggle icon
    function updateThemeToggleIcon(theme) {
        const toggleBtn = document.getElementById('themeToggle');
        if (toggleBtn) {
            if (theme === 'dark') {
                toggleBtn.innerHTML = '<i class="bi bi-sun-fill"></i>';
                toggleBtn.title = 'Switch to Light Theme';
            } else {
                toggleBtn.innerHTML = '<i class="bi bi-moon-fill"></i>';
                toggleBtn.title = 'Switch to Dark Theme';
            }
        }
    }
    
    // Toggle theme
    function toggleTheme() {
        const currentTheme = getTheme();
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
    }
    
    // Initialize theme on page load
    function initTheme() {
        const theme = getTheme();
        setTheme(theme);
    }
    
    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTheme);
    } else {
        initTheme();
    }
    
    // Make toggleTheme available globally
    window.toggleTheme = toggleTheme;
})();

