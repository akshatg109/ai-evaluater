(function () {
    const forms = document.querySelectorAll('[data-auth-form]');

    document.querySelectorAll('[data-toggle-password]').forEach((button) => {
        button.addEventListener('click', () => {
            const input = document.querySelector(button.dataset.togglePassword);
            if (!input) return;
            const visible = input.type === 'text';
            input.type = visible ? 'password' : 'text';
            button.textContent = visible ? 'Show' : 'Hide';
            button.setAttribute('aria-label', visible ? 'Show password' : 'Hide password');
        });
    });

    const password = document.querySelector('#password');
    const confirmPassword = document.querySelector('#confirmPassword');
    const checks = document.querySelectorAll('[data-password-check]');

    function updatePasswordChecks() {
        if (!password || !checks.length) return;

        const value = password.value;
        const matches = !confirmPassword || (confirmPassword.value && confirmPassword.value === value);
        const validations = {
            length: value.length >= 8,
            number: /\d/.test(value),
            match: matches
        };

        checks.forEach((check) => {
            const valid = validations[check.dataset.passwordCheck];
            check.classList.toggle('valid', Boolean(valid));
            check.textContent = `${valid ? '✓' : '○'} ${check.dataset.label}`;
        });
    }

    [password, confirmPassword].forEach((input) => {
        if (input) input.addEventListener('input', updatePasswordChecks);
    });

    forms.forEach((form) => {
        form.addEventListener('submit', (event) => {
            const button = form.querySelector('button[type="submit"]');
            const email = form.querySelector('input[type="email"]');

            if (email && !email.validity.valid) {
                email.setAttribute('aria-invalid', 'true');
                return;
            }

            if (confirmPassword && password && confirmPassword.value !== password.value) {
                event.preventDefault();
                confirmPassword.setAttribute('aria-invalid', 'true');
                const message = document.querySelector('#signupMessage');
                if (message) {
                    message.className = 'alert-custom error visible';
                    message.textContent = '⚠️ Passwords must match.';
                }
                return;
            }

            if (button) {
                button.disabled = true;
                button.textContent = button.dataset.loadingText || 'Please wait...';
            }
        });
    });

    updatePasswordChecks();
})();
