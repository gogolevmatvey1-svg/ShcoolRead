// ===== API Configuration =====
const API_BASE = '/api';

// ===== State =====
let adminSessionId = null;
let searchTimeout = null;
let currentUserName = '';
let currentUserGrade = '';
let currentUserRole = ''; // 'student', 'admin', 'librarian'

// ===== Utility Functions =====

function showNotification(message, type = 'info') {
    const el = document.getElementById('notification');
    el.textContent = message;
    el.className = `notification ${type} show`;
    setTimeout(() => el.classList.remove('show'), 3000);
}

function debounceSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(applyFilters, 300);
}

function showPage(pageId) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.getElementById(pageId).classList.add('active');
}

// ===== API Calls =====

async function apiFetch(url, options = {}) {
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers,
    };
    if (adminSessionId) {
        headers['X-Session-Id'] = adminSessionId;
    }
    const response = await fetch(`${API_BASE}${url}`, {
        ...options,
        headers,
    });
    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: 'Ошибка сервера' }));
        throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return response.json();
}

// ===== Login / Auth =====

function switchLoginTab(tab, btn) {
    document.querySelectorAll('.login-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.login-tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(tab === 'student' ? 'studentLogin' : 'librarianLogin').classList.add('active');
}

// ---- Student Register ----

function showStudentRegister() {
    document.getElementById('studentLogin').querySelector('form').style.display = 'none';
    document.getElementById('studentRegisterForm').style.display = 'block';
}

function hideStudentRegister() {
    document.getElementById('studentRegisterForm').style.display = 'none';
    document.getElementById('studentLogin').querySelector('form').style.display = 'block';
}

async function studentRegister(e) {
    e.preventDefault();
    const name = document.getElementById('regName').value.trim();
    const grade = document.getElementById('regGrade').value;
    const password = document.getElementById('regPassword').value;
    const passwordRepeat = document.getElementById('regPasswordRepeat').value;

    if (!name || !grade || !password) {
        showNotification('Заполните все поля', 'error');
        return;
    }
    if (password !== passwordRepeat) {
        showNotification('Пароли не совпадают', 'error');
        return;
    }
    if (password.length < 4) {
        showNotification('Пароль должен быть не менее 4 символов', 'error');
        return;
    }

    try {
        const result = await apiFetch('/register', {
            method: 'POST',
            body: JSON.stringify({ name, grade, password }),
        });
        showNotification('Регистрация успешна!', 'success');
        currentUserName = result.user.name;
        currentUserGrade = result.user.grade;
        currentUserRole = 'student';
        document.getElementById('userNameDisplay').textContent = result.user.name;
        hideStudentRegister();
        showPage('catalogPage');
        loadFilters();
        loadBooks();
    } catch (err) {
        showNotification(err.message, 'error');
    }
}

// ---- Student Login ----

async function studentLogin(e) {
    e.preventDefault();
    const name = document.getElementById('studentNameInput').value.trim();
    const password = document.getElementById('studentPassword').value;

    if (!name || !password) {
        showNotification('Введите имя и пароль', 'error');
        return;
    }

    try {
        const result = await apiFetch('/login', {
            method: 'POST',
            body: JSON.stringify({ name, password }),
        });
        currentUserName = result.user.name;
        currentUserGrade = result.user.grade;
        currentUserRole = 'student';
        document.getElementById('userNameDisplay').textContent = result.user.name;
        showNotification('Вход выполнен!', 'success');
        showPage('catalogPage');
        loadFilters();
        loadBooks();
    } catch (err) {
        showNotification(err.message, 'error');
    }
}

function logoutToLogin() {
    currentUserName = '';
    currentUserRole = '';
    currentUserGrade = '';
    adminSessionId = null;
    document.getElementById('studentNameInput').value = '';
    document.getElementById('studentPassword').value = '';
    document.getElementById('userNameDisplay').textContent = '';
    document.getElementById('borrowerName').value = '';
    hideStudentRegister();
    showPage('loginPage');
}

async function adminLogin(e) {
    e.preventDefault();
    const email = document.getElementById('loginEmail').value;
    const password = document.getElementById('loginPassword').value;

    try {
        const result = await apiFetch('/admin/login', {
            method: 'POST',
            body: JSON.stringify({ email, password }),
        });
        adminSessionId = result.session_id;
        currentUserRole = 'admin';
        showNotification('Вход выполнен успешно', 'success');
        showPage('adminPage');
        loadAdminStats();
        loadAdminBooks();
        loadAdminLoans();
    } catch (err) {
        showNotification(err.message, 'error');
    }
}

async function adminLogout() {
    try {
        await apiFetch('/admin/logout', { method: 'POST' });
    } catch (_) {}
    adminSessionId = null;
    currentUserRole = '';
    showNotification('Вы вышли из системы', 'info');
    showPage('loginPage');
}

function goToCatalog() {
    if (!currentUserName) {
        currentUserName = 'Администратор';
    }
    document.getElementById('userNameDisplay').textContent = currentUserName;
    showPage('catalogPage');
    loadFilters();
    loadBooks();
    // Highlight nav
    document.querySelectorAll('#catalogPage .nav-item, #adminPage .nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector('#catalogPage .nav-item:first-child')?.classList.add('active');
}

function switchToAdmin() {
    if (!adminSessionId) {
        showNotification('Сначала войдите как администратор', 'error');
        return;
    }
    showPage('adminPage');
    loadAdminStats();
    loadAdminBooks();
    loadAdminLoans();
    // Highlight nav
    document.querySelectorAll('#catalogPage .nav-item, #adminPage .nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector('#adminPage .nav-item:last-child')?.classList.add('active');
}

// ===== Load Books =====

async function loadBooks() {
    const params = new URLSearchParams();
    const author = document.getElementById('filterAuthor').value;
    const grade = document.getElementById('filterGrade').value;
    const purpose = document.getElementById('filterPurpose').value;
    const search = document.getElementById('searchInput').value;

    if (author) params.set('author', author);
    if (grade) params.set('grade', grade);
    if (purpose) params.set('purpose', purpose);
    if (search) params.set('search', search);

    try {
        const books = await apiFetch(`/books?${params.toString()}`);
        renderBooks(books);
    } catch (err) {
        document.getElementById('booksGrid').innerHTML = `<div class="loading" style="color:var(--danger)">Ошибка загрузки: ${err.message}</div>`;
    }
}

function renderBooks(books) {
    const grid = document.getElementById('booksGrid');
    if (books.length === 0) {
        grid.innerHTML = '<div class="loading">Книги не найдены</div>';
        return;
    }
    grid.innerHTML = books.map(book => {
        const isAvailable = book.available_copies > 0;
        const isLow = book.available_copies <= 2 && book.available_copies > 0;
        const statusClass = isAvailable ? (isLow ? 'low-stock' : 'in-stock') : 'out-of-stock';
        const statusText = isAvailable ? (isLow ? `Осталось ${book.available_copies}` : `В наличии: ${book.available_copies}`) : 'Нет в наличии';

        const coverHtml = book.cover_url
            ? `<img class="book-cover" src="${book.cover_url}" alt="${book.title}" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'" loading="lazy"><div class="book-cover-placeholder" style="display:none">📖</div>`
            : `<div class="book-cover-placeholder">📖</div>`;

        return `
            <div class="book-card" onclick="openDetailModal(${book.id})">
                ${coverHtml}
                <div class="book-info">
                    <div class="book-title">${escapeHtml(book.title)}</div>
                    <div class="book-author">${escapeHtml(book.author)}</div>
                    <div class="book-meta">
                        ${book.grade ? `<span class="book-tag primary">${escapeHtml(book.grade)} класс</span>` : ''}
                        ${book.purpose ? `<span class="book-tag">${escapeHtml(book.purpose)}</span>` : ''}
                    </div>
                    <div class="book-available">
                        <span class="${statusClass}">${statusText}</span>
                    </div>
                    <div style="display:flex;gap:8px;">
                        <button class="btn btn-sm ${isAvailable ? 'btn-primary' : 'btn-secondary'}" 
                                onclick="event.stopPropagation();openBookingModal(${book.id})" 
                                ${!isAvailable ? 'disabled' : ''}>
                            ${isAvailable ? 'Забронировать' : 'Нет в наличии'}
                        </button>
                        <button class="btn btn-sm btn-outline" onclick="event.stopPropagation();openDetailModal(${book.id})">
                            Подробнее
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ===== Filters =====

async function loadFilters() {
    try {
        const filters = await apiFetch('/filters');
        const authorSelect = document.getElementById('filterAuthor');
        const gradeSelect = document.getElementById('filterGrade');
        const purposeSelect = document.getElementById('filterPurpose');

        authorSelect.innerHTML = '<option value="">Все авторы</option>' +
            filters.authors.map(a => `<option value="${escapeHtml(a)}">${escapeHtml(a)}</option>`).join('');

        gradeSelect.innerHTML = '<option value="">Все классы</option>' +
            filters.grades.map(g => `<option value="${escapeHtml(g)}">${escapeHtml(g)} класс</option>`).join('');

        purposeSelect.innerHTML = '<option value="">Все цели</option>' +
            filters.purposes.map(p => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`).join('');
    } catch (err) {
        console.error('Failed to load filters:', err);
    }
}

function applyFilters() {
    loadBooks();
}

function resetFilters() {
    document.getElementById('filterAuthor').value = '';
    document.getElementById('filterGrade').value = '';
    document.getElementById('filterPurpose').value = '';
    document.getElementById('searchInput').value = '';
    applyFilters();
}

// ===== Detail Modal =====

let detailModalBookId = null;

async function openDetailModal(bookId) {
    try {
        const book = await apiFetch(`/books/${bookId}`);
        detailModalBookId = book.id;

        document.getElementById('detailTitle').textContent = book.title;
        document.getElementById('detailAuthor').textContent = book.author;
        document.getElementById('detailGrade').textContent = book.grade ? `${book.grade} класс` : '';
        document.getElementById('detailPurpose').textContent = book.purpose || '';
        document.getElementById('detailYear').textContent = book.year ? `Год издания: ${book.year}` : '';

        const availableText = book.available_copies > 0
            ? `✅ В наличии: ${book.available_copies} из ${book.total_copies}`
            : '❌ Нет в наличии';
        document.getElementById('detailAvailable').textContent = availableText;

        const desc = document.getElementById('detailDescription');
        if (book.description) {
            desc.textContent = book.description;
            desc.style.display = 'block';
        } else {
            desc.textContent = 'Описание отсутствует';
            desc.style.display = 'block';
            desc.style.color = 'var(--gray-400)';
            desc.style.fontStyle = 'italic';
        }

        const bookingBtn = document.getElementById('detailBookingBtn');
        if (book.available_copies > 0) {
            bookingBtn.disabled = false;
            bookingBtn.textContent = 'Забронировать';
            bookingBtn.className = 'btn btn-primary btn-full btn-lg';
        } else {
            bookingBtn.disabled = true;
            bookingBtn.textContent = 'Нет в наличии';
            bookingBtn.className = 'btn btn-secondary btn-full btn-lg';
        }

        document.getElementById('detailModal').classList.add('active');
    } catch (err) {
        showNotification(err.message, 'error');
    }
}

function closeDetailModal() {
    document.getElementById('detailModal').classList.remove('active');
    detailModalBookId = null;
}

function openBookingModalFromDetail() {
    if (detailModalBookId) {
        closeDetailModal();
        openBookingModal(detailModalBookId);
    }
}

// ===== Booking Modal =====

async function openBookingModal(bookId) {
    if (!currentUserName) {
        showNotification('Пожалуйста, войдите в систему', 'error');
        return;
    }
    try {
        const book = await apiFetch(`/books/${bookId}`);

        document.getElementById('bookId').value = book.id;
        document.getElementById('modalCover').src = book.cover_url || '';
        document.getElementById('modalCover').onerror = function() { this.style.display = 'none'; };
        document.getElementById('modalTitle').textContent = book.title;
        document.getElementById('modalAuthor').textContent = book.author;
        document.getElementById('modalAvailable').textContent = `Доступно: ${book.available_copies} из ${book.total_copies}`;
        document.getElementById('quantity').max = book.available_copies;
        document.getElementById('quantity').value = 1;
        document.getElementById('borrowerName').value = currentUserName;

        document.getElementById('bookingModal').classList.add('active');
    } catch (err) {
        showNotification(err.message, 'error');
    }
}

function closeModal() {
    document.getElementById('bookingModal').classList.remove('active');
}

function toggleCustomPurpose() {
    const select = document.getElementById('purposeSelect');
    const custom = document.getElementById('customPurpose');
    if (select.value === 'other') {
        custom.style.display = 'block';
        custom.required = true;
    } else {
        custom.style.display = 'none';
        custom.required = false;
    }
}

async function submitBooking(e) {
    e.preventDefault();

    const bookId = document.getElementById('bookId').value;
    const borrowerName = document.getElementById('borrowerName').value.trim();
    let purpose = document.getElementById('purposeSelect').value;
    if (purpose === 'other') {
        purpose = document.getElementById('customPurpose').value.trim();
    }
    const quantity = parseInt(document.getElementById('quantity').value);

    const btn = e.target.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.textContent = 'Бронирование...';

    try {
        const result = await apiFetch('/loans', {
            method: 'POST',
            body: JSON.stringify({
                book_id: parseInt(bookId),
                borrower_name: borrowerName,
                purpose: purpose,
                quantity: quantity,
            }),
        });

        closeModal();
        showNotification(`Книга "${document.getElementById('modalTitle').textContent}" успешно забронирована!`, 'success');
        loadBooks();
        e.target.reset();
        document.getElementById('purposeSelect').value = 'урок';
        document.getElementById('customPurpose').style.display = 'none';
    } catch (err) {
        showNotification(err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Забронировать';
    }
}

// ===== Admin Panel =====

function switchAdminTab(tab, btn) {
    document.querySelectorAll('.admin-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.admin-tab-content').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');

    const tabNames = { books: 'Books', loans: 'Loans', popular: 'Popular' };
    document.getElementById(`adminTab${tabNames[tab]}`).classList.add('active');

    if (tab === 'books') loadAdminBooks();
    if (tab === 'loans') loadAdminLoans();
    if (tab === 'popular') loadAdminStats();
}

async function loadAdminStats() {
    try {
        const stats = await apiFetch('/admin/stats');
        document.getElementById('statTotalBooks').textContent = stats.total_books || 0;
        document.getElementById('statActiveLoans').textContent = stats.active_loans || 0;
        document.getElementById('statReturnedToday').textContent = stats.returned_today || 0;

        const topList = document.getElementById('topBooksList');
        if (stats.top_books && stats.top_books.length > 0) {
            const books = await apiFetch('/books');
            const bookMap = {};
            books.forEach(b => bookMap[b.id] = b);

            topList.innerHTML = stats.top_books.map((item, i) => {
                const book = bookMap[item.book_id];
                const title = book ? book.title : `Книга #${item.book_id}`;
                let rankClass = '';
                if (i === 0) rankClass = 'gold';
                else if (i === 1) rankClass = 'silver';
                else if (i === 2) rankClass = 'bronze';
                return `
                    <div class="top-book-item">
                        <div class="top-book-rank ${rankClass}">${i + 1}</div>
                        <span class="top-book-title">${escapeHtml(title)}</span>
                        <span class="top-book-views">${item.views} просмотров</span>
                    </div>
                `;
            }).join('');
        } else {
            topList.innerHTML = '<p style="color:var(--gray-400);padding:12px 0;">Пока нет данных. Просматривайте книги, чтобы собрать статистику.</p>';
        }
    } catch (err) {
        showNotification('Ошибка загрузки статистики', 'error');
    }
}

// ===== Admin: Books =====

async function loadAdminBooks() {
    try {
        const books = await apiFetch('/books');
        const tbody = document.getElementById('adminBooksBody');
        const count = document.getElementById('adminBooksCount');

        if (count) count.textContent = `${books.length} книг`;

        tbody.innerHTML = books.map(book => {
            const coverHtml = book.cover_url
                ? `<img class="book-cover-thumb" src="${book.cover_url}" alt="" onerror="this.style.display='none';this.parentElement.textContent='📖'">`
                : '📖';
            return `
                <tr>
                    <td>${coverHtml}</td>
                    <td><strong>${escapeHtml(book.title)}</strong></td>
                    <td>${escapeHtml(book.author)}</td>
                    <td>${book.grade || '-'}</td>
                    <td>${book.total_copies}</td>
                    <td>${book.available_copies}</td>
                    <td>
                        <button class="btn btn-sm btn-secondary" onclick="editBook(${book.id})" title="Редактировать">✏️</button>
                        <button class="btn btn-sm btn-danger" onclick="deleteBook(${book.id})" title="Удалить" style="margin-left:4px;">🗑️</button>
                    </td>
                </tr>
            `;
        }).join('');
    } catch (err) {
        showNotification('Ошибка загрузки книг', 'error');
    }
}

function filterAdminBooks() {
    const query = document.getElementById('adminBookSearch').value.toLowerCase().trim();
    const rows = document.querySelectorAll('#adminBooksBody tr');
    let visible = 0;
    rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        if (!query || text.includes(query)) {
            row.style.display = '';
            visible++;
        } else {
            row.style.display = 'none';
        }
    });
    const count = document.getElementById('adminBooksCount');
    if (count) count.textContent = `${visible} из ${rows.length} книг`;
}

function showAddBookForm() {
    document.getElementById('bookFormTitle').textContent = 'Добавить новую книгу';
    document.getElementById('editBookId').value = '';
    document.getElementById('fTitle').value = '';
    document.getElementById('fAuthor').value = '';
    document.getElementById('fYear').value = '';
    document.getElementById('fGrade').value = '';
    document.getElementById('fPurpose').value = 'учебник';
    document.getElementById('fTotalCopies').value = '1';
    document.getElementById('fCoverUrl').value = '';
    document.getElementById('bookFormPanel').style.display = 'block';
    document.getElementById('bookFormPanel').scrollIntoView({ behavior: 'smooth' });
}

async function editBook(bookId) {
    try {
        const books = await apiFetch('/books');
        const book = books.find(b => b.id === bookId);
        if (!book) return;

        document.getElementById('bookFormTitle').textContent = 'Редактировать книгу';
        document.getElementById('editBookId').value = book.id;
        document.getElementById('fTitle').value = book.title;
        document.getElementById('fAuthor').value = book.author;
        document.getElementById('fYear').value = book.year || '';
        document.getElementById('fGrade').value = book.grade || '';
        document.getElementById('fPurpose').value = book.purpose || 'учебник';
        document.getElementById('fTotalCopies').value = book.total_copies;
        document.getElementById('fCoverUrl').value = book.cover_url || '';
        document.getElementById('bookFormPanel').style.display = 'block';
        document.getElementById('bookFormPanel').scrollIntoView({ behavior: 'smooth' });
    } catch (err) {
        showNotification('Ошибка загрузки данных книги', 'error');
    }
}

function cancelBookForm() {
    document.getElementById('bookFormPanel').style.display = 'none';
}

async function saveBook(e) {
    e.preventDefault();
    const editId = document.getElementById('editBookId').value;
    const data = {
        title: document.getElementById('fTitle').value,
        author: document.getElementById('fAuthor').value,
        year: parseInt(document.getElementById('fYear').value) || null,
        grade: document.getElementById('fGrade').value || null,
        purpose: document.getElementById('fPurpose').value || null,
        total_copies: parseInt(document.getElementById('fTotalCopies').value),
        cover_url: document.getElementById('fCoverUrl').value || null,
    };

    try {
        if (editId) {
            await apiFetch(`/admin/books/${editId}`, { method: 'PUT', body: JSON.stringify(data) });
            showNotification('Книга обновлена', 'success');
        } else {
            await apiFetch('/admin/books', { method: 'POST', body: JSON.stringify(data) });
            showNotification('Книга добавлена', 'success');
        }
        cancelBookForm();
        await loadAdminBooks();
        await loadBooks();
    } catch (err) {
        showNotification(err.message, 'error');
    }
}

async function deleteBook(bookId) {
    if (!confirm('Вы уверены, что хотите удалить эту книгу?')) return;

    try {
        await apiFetch(`/admin/books/${bookId}`, { method: 'DELETE' });
        showNotification('Книга удалена', 'success');
        await loadAdminBooks();
        await loadBooks();
    } catch (err) {
        showNotification(err.message, 'error');
    }
}

// ===== Admin: Loans =====

async function loadAdminLoans() {
    try {
        const status = document.getElementById('loanFilter').value;
        const params = status ? `?status=${status}` : '';
        const loans = await apiFetch(`/admin/loans${params}`);
        const tbody = document.getElementById('adminLoansBody');
        tbody.innerHTML = loans.map(loan => `
            <tr>
                <td><strong>${escapeHtml(loan.book_title)}</strong></td>
                <td>${escapeHtml(loan.borrower_name)}</td>
                <td>${escapeHtml(loan.purpose || '-')}</td>
                <td>${loan.quantity}</td>
                <td>${formatDate(loan.date_borrowed)}</td>
                <td><span class="status-badge ${loan.status}">${loan.status === 'active' ? 'Активно' : 'Возвращена'}</span></td>
                <td>
                    ${loan.status === 'active'
                        ? `<button class="btn btn-sm btn-primary" onclick="returnBook(${loan.id})">✅ Отметить возврат</button>`
                        : `<span style="color:var(--gray-400);font-size:13px;">${loan.date_returned ? formatDate(loan.date_returned) : '-'}</span>`
                    }
                </td>
            </tr>
        `).join('');
    } catch (err) {
        showNotification('Ошибка загрузки бронирований', 'error');
    }
}

async function returnBook(loanId) {
    if (!confirm('Отметить книгу как возвращённую?')) return;

    try {
        await apiFetch(`/admin/loans/${loanId}/return`, { method: 'POST' });
        showNotification('Книга отмечена как возвращённая', 'success');
        await loadAdminLoans();
        await loadAdminStats();
        await loadBooks();
    } catch (err) {
        showNotification(err.message, 'error');
    }
}

function formatDate(dateStr) {
    if (!dateStr) return '-';
    const d = new Date(dateStr);
    return d.toLocaleDateString('ru-RU', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
    });
}

// ===== Theme Toggle =====

function toggleTheme() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    if (isDark) {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('theme', 'light');
    } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('theme', 'dark');
    }
}

// Restore saved theme
if (localStorage.getItem('theme') === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
}

// ===== Initialize =====

document.addEventListener('DOMContentLoaded', () => {
    showPage('loginPage');
});
