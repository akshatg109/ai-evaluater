(function () {
    const toggle = document.querySelector('[data-nav-toggle]');
    const links = document.querySelector('#appNavLinks');

    if (!toggle || !links) return;

    toggle.addEventListener('click', () => {
        const isOpen = links.classList.toggle('open');
        toggle.setAttribute('aria-expanded', String(isOpen));
        toggle.setAttribute('aria-label', isOpen ? 'Close navigation' : 'Open navigation');
    });
})();
