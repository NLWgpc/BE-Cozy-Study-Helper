// Authentication logic

const API_BASE = window.API_BASE;

function setToken(token) {
    localStorage.setItem('auth_token', token);
}

function getToken() {
    return localStorage.getItem('auth_token') || localStorage.getItem('token');
}

function logout() {
    localStorage.removeItem('auth_token');
    localStorage.removeItem('token');
    window.location.href = '/login';
}

function getAuthHeaders() {
    const token = getToken();
    return token ? { 'Authorization': `Bearer ${token}` } : {};
}

async function checkAuth() {
    const token = getToken();
    const currentPath = window.location.pathname;
    const protectedRoutes = ['/', '/solve', '/practice', '/history'];
    const authContainer = document.getElementById('auth-buttons');
    
    if (token) {
        try {
            const res = await fetch(`${API_BASE}/auth/me`, {
                headers: getAuthHeaders()
            });
            if (!res.ok) throw new Error('Invalid token');
            
            // Logged in user
            if (authContainer) {
                authContainer.innerHTML = `
                    <button class="btn btn-secondary" onclick="logout()">
                        <span class="material-symbols-outlined">logout</span>
                        Log out
                    </button>
                `;
            }
            if (currentPath === '/login') {
                window.location.href = '/';
            }
        } catch (err) {
            console.error(err);
            logout();
        }
    } else {
        // Not logged in
        if (authContainer) {
            authContainer.innerHTML = `
                <a href="/login" class="btn btn-primary">
                    <span class="material-symbols-outlined">login</span>
                    Log in
                </a>
            `;
        }
        
        // Redirect if trying to access protected route
        if (protectedRoutes.includes(currentPath)) {
            window.location.href = '/login';
        }
    }
}

// Setup Event Listeners for Login/Register if elements exist
document.addEventListener('DOMContentLoaded', () => {
    checkAuth();
    
    const loginForm = document.getElementById('login-form');
    if (loginForm) {
        loginForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('login-btn');
            btn.innerHTML = '<div class="loader"></div>';
            btn.disabled = true;
            
            const email = document.getElementById('login-email').value;
            const password = document.getElementById('login-password').value;
            
            try {
                const res = await fetch(`${API_BASE}/auth/login`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password })
                });
                
                const data = await res.json();
                if (res.ok) {
                    setToken(data.access_token);
                    window.location.href = '/';
                } else {
                    showToast(data.detail || 'Login failed', true);
                    btn.innerHTML = 'Log in';
                    btn.disabled = false;
                }
            } catch (err) {
                showToast('Network error', true);
                btn.innerHTML = 'Log in';
                btn.disabled = false;
            }
        });
    }
    
    const registerForm = document.getElementById('register-form');
    if (registerForm) {
        registerForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const btn = document.getElementById('register-btn');
            
            const email = document.getElementById('reg-email').value;
            const password = document.getElementById('reg-password').value;
            const confirm = document.getElementById('reg-confirm').value;
            
            if (password !== confirm) {
                showToast('Passwords do not match', true);
                return;
            }
            
            btn.innerHTML = '<div class="loader"></div>';
            btn.disabled = true;
            
            try {
                const res = await fetch(`${API_BASE}/auth/register`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ email, password })
                });
                
                const data = await res.json();
                if (res.ok) {
                    setToken(data.access_token);
                    window.location.href = '/';
                } else {
                    showToast(data.detail || 'Registration failed', true);
                    btn.innerHTML = 'Create account';
                    btn.disabled = false;
                }
            } catch (err) {
                showToast('Network error', true);
                btn.innerHTML = 'Create account';
                btn.disabled = false;
            }
        });
    }
});
