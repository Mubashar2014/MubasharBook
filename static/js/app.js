/* =============================================
   Mubashar's Book — JavaScript v2
   ============================================= */

// ============ SIDEBAR TOGGLE ============
function toggleSidebar() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    sidebar.classList.toggle('open');
    overlay.classList.toggle('open');
}

document.addEventListener('click', (e) => {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.sidebar-overlay');
    const toggle = document.querySelector('.sidebar-toggle');
    if (sidebar && sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) && e.target !== toggle && !toggle?.contains(e.target)) {
        sidebar.classList.remove('open');
        overlay?.classList.remove('open');
    }
});

// ============ SCROLL REVEAL ============
function initScrollReveal() {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach((entry) => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.1, rootMargin: '0px 0px -40px 0px' });

    document.querySelectorAll('.animate-on-scroll').forEach((el) => {
        observer.observe(el);
    });
}

// ============ NUMBER COUNTER ============
function animateCounters() {
    document.querySelectorAll('.hero-stat-value[data-count]').forEach((el) => {
        const target = parseInt(el.dataset.count, 10);
        if (isNaN(target) || target === 0) return;

        const duration = 800;
        const start = performance.now();

        function formatValue(val) {
            if (val >= 100000) return 'Rs ' + (val / 100000).toFixed(1) + 'L';
            return 'Rs ' + val.toLocaleString('en-IN');
        }

        function update(now) {
            const elapsed = now - start;
            const progress = Math.min(elapsed / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 3);
            const current = Math.round(eased * target);
            el.textContent = formatValue(current);
            if (progress < 1) requestAnimationFrame(update);
        }
        requestAnimationFrame(update);
    });
}

// ============ NAV SCROLL ============
function initNavScroll() {
    const nav = document.getElementById('mkt-nav');
    if (!nav) return;
    window.addEventListener('scroll', () => {
        nav.classList.toggle('scrolled', window.scrollY > 20);
    }, { passive: true });
}

// ============ SMOOTH SCROLL ============
document.querySelectorAll('a[href^="#"]').forEach((a) => {
    a.addEventListener('click', (e) => {
        const id = a.getAttribute('href');
        if (id === '#') return;
        const target = document.querySelector(id);
        if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});

// ============ INIT ============
document.addEventListener('DOMContentLoaded', () => {
    initScrollReveal();
    initNavScroll();
    setTimeout(animateCounters, 300);
});
