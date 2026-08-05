/* ============================================================
   OracleForge — main.js
   Shared site behavior: mobile nav toggle + waitlist form handler
   ============================================================ */

(function () {
    'use strict';

    // ---------- Mobile nav toggle ----------
    const navToggle = document.getElementById('navToggle');
    const navLinks = document.getElementById('navLinks');

    if (navToggle && navLinks) {
        navToggle.addEventListener('click', function () {
            navLinks.classList.toggle('open');
        });
    }

    // ---------- Shared waitlist form handler ----------
    // Handles any form with id="waitlistForm" (home + waitlist pages).
    const waitlistForm = document.getElementById('waitlistForm');
    if (waitlistForm) {
        waitlistForm.addEventListener('submit', async function (e) {
            e.preventDefault();

            const email = encodeURIComponent(waitlistForm.email.value.trim());
            const name = encodeURIComponent(
                (waitlistForm.name ? waitlistForm.name.value : '') || ''
            );
            const referredBy = encodeURIComponent(
                (waitlistForm.referred_by ? waitlistForm.referred_by.value : '') || ''
            );

            const msg = document.getElementById('formMessage');
            const refBox = document.getElementById('referralCode');

            try {
                const res = await fetch('/api/waitlist', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: 'email=' + email + '&name=' + name + '&referred_by=' + referredBy
                });
                const data = await res.json();

                if (data.success) {
                    if (msg) {
                        msg.innerHTML = '<div class="form-success">✅ You are on the list, anon! Welcome to the cult.</div>';
                    }
                    if (refBox && data.referral_code) {
                        refBox.textContent = 'Your referral code: ' + data.referral_code;
                    }
                    waitlistForm.reset();
                } else {
                    if (msg) {
                        msg.innerHTML = '<div class="form-error" style="display:block;">⚠️ ' +
                            (data.error || 'Something went wrong') + '</div>';
                    }
                }
            } catch (err) {
                if (msg) {
                    msg.innerHTML = '<div class="form-error" style="display:block;">⚠️ Network error: ' +
                        String(err) + '</div>';
                }
            }
        });
    }
})();