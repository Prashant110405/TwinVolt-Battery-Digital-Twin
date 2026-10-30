/**
 * TwinVolt Landing Page Isometric Battery Visualization & Interactive Controls
 * Uses standard Canvas2D isometric rendering without heavyweight external frameworks.
 * Lightweight, hardware-accelerated, and includes an instant static fallback.
 */

(function () {
  'use strict';

  function initBattery3DVisualizer() {
    const canvas = document.getElementById('battery-3d-canvas');
    const fallback = document.getElementById('battery-fallback');
    if (!canvas) return;

    // Respect reduced motion preference
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    const ctx = canvas.getContext('2d');
    if (!ctx) {
      if (fallback) fallback.style.display = 'flex';
      return;
    }

    let animationFrameId = null;
    let angle = 0.45;
    let width = 0;
    let height = 0;

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      width = rect.width;
      height = rect.height;
      canvas.width = width * dpr;
      canvas.height = height * dpr;
      ctx.scale(dpr, dpr);
    }

    resize();
    window.addEventListener('resize', resize, { passive: true });

    // Hide fallback once canvas is initialized
    if (fallback) fallback.style.display = 'none';

    function drawIsoBatteryCell(cx, cy, radius, cellHeight, currentAngle, colorAccent) {
      ctx.save();
      ctx.translate(cx, cy);

      // Isometric projection tilt
      const rx = radius;
      const ry = radius * 0.45;

      // Cell Base Shadow
      ctx.beginPath();
      ctx.ellipse(0, cellHeight / 2 + 10, rx * 1.15, ry * 1.15, 0, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(20, 36, 58, 0.08)';
      ctx.fill();

      // Lower Cylinder Body
      const grad = ctx.createLinearGradient(-rx, 0, rx, 0);
      grad.addColorStop(0, '#CBD5E1');
      grad.addColorStop(0.2, '#F1F5F9');
      grad.addColorStop(0.5, '#FFFFFF');
      grad.addColorStop(0.8, '#E2E8F0');
      grad.addColorStop(1, '#94A3B8');

      ctx.beginPath();
      ctx.ellipse(0, cellHeight / 2, rx, ry, 0, 0, Math.PI);
      ctx.lineTo(rx, -cellHeight / 2);
      ctx.ellipse(0, -cellHeight / 2, rx, ry, 0, 0, Math.PI, true);
      ctx.closePath();
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.strokeStyle = '#CBD5E1';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Technical Accent Band
      ctx.beginPath();
      ctx.ellipse(0, -cellHeight / 4, rx + 0.2, ry + 0.2, 0, 0, Math.PI * 2);
      ctx.strokeStyle = colorAccent;
      ctx.lineWidth = 2.5;
      ctx.stroke();

      // Cylinder Top Face
      ctx.beginPath();
      ctx.ellipse(0, -cellHeight / 2, rx, ry, 0, 0, Math.PI * 2);
      ctx.fillStyle = '#F8FAFC';
      ctx.fill();
      ctx.strokeStyle = '#CBD5E1';
      ctx.stroke();

      // Positive Terminal Stud
      const termRx = rx * 0.38;
      const termRy = ry * 0.38;
      const termH = 12;

      ctx.beginPath();
      ctx.ellipse(0, -cellHeight / 2 - termH, termRx, termRy, 0, 0, Math.PI * 2);
      ctx.fillStyle = '#E2E8F0';
      ctx.fill();
      ctx.strokeStyle = '#94A3B8';
      ctx.stroke();

      // Pulse Energy Field
      ctx.beginPath();
      ctx.ellipse(0, -cellHeight / 2 - termH, termRx * 0.7, termRy * 0.7, 0, 0, Math.PI * 2);
      ctx.fillStyle = colorAccent;
      ctx.fill();

      ctx.restore();
    }

    function render() {
      ctx.clearRect(0, 0, width, height);

      const cx = width / 2;
      const cy = height / 2 + 10;
      const cellHeight = 160;
      const radius = 55;

      // Animate rotation subtly
      if (!prefersReducedMotion) {
        angle += 0.008;
      }

      // Draw multi-cell pack module
      drawIsoBatteryCell(cx - 75, cy + 25, radius * 0.85, cellHeight * 0.9, angle, '#12A9C7');
      drawIsoBatteryCell(cx + 75, cy + 25, radius * 0.85, cellHeight * 0.9, angle, '#3188F5');
      drawIsoBatteryCell(cx, cy - 20, radius, cellHeight, angle, '#1769D2');

      if (!prefersReducedMotion) {
        animationFrameId = requestAnimationFrame(render);
      }
    }

    // Lazy load when in viewport
    if ('IntersectionObserver' in window) {
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              if (!animationFrameId) render();
            } else {
              if (animationFrameId) {
                cancelAnimationFrame(animationFrameId);
                animationFrameId = null;
              }
            }
          });
        },
        { threshold: 0.1 }
      );
      observer.observe(canvas);
    } else {
      render();
    }
  }

  // Smooth anchor scrolling
  function setupSmoothScroll() {
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
      anchor.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (href.length > 1) {
          const target = document.querySelector(href);
          if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth' });
          }
        }
      });
    });
  }

  // Initialize once DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      initBattery3DVisualizer();
      setupSmoothScroll();
    });
  } else {
    initBattery3DVisualizer();
    setupSmoothScroll();
  }
})();
