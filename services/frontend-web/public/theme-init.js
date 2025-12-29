(function() {
  try {
    var theme = localStorage.getItem('theme') || 'system';
    var resolvedTheme = theme;
    if (theme === 'system') {
      resolvedTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    document.documentElement.setAttribute('data-theme', resolvedTheme);
    if (resolvedTheme === 'dark') {
      document.documentElement.classList.add('dark');
    }
  } catch (e) {}
})();
