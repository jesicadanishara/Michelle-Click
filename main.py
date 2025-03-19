import os
from flask import Flask, render_template, url_for, request, redirect, flash, session
import sqlite3 as sql
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.secret_key = os.environ.get('SECRET_KEY', 'default_secret_key')  # Use environment variable for secret key

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

def init_db():
    with sql.connect('rental.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                contact TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'user'))
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                price INTEGER NOT NULL,
                stock INTEGER DEFAULT 1,
                image TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                contact TEXT NOT NULL,
                book_date TEXT NOT NULL,
                return_date TEXT NOT NULL,
                duration INTEGER NOT NULL,
                total_price INTEGER NOT NULL,
                down_payment INTEGER NOT NULL,
                payment_method TEXT NOT NULL,
                payment_proof TEXT NOT NULL,
                status TEXT DEFAULT 'Pending',
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                contact TEXT NOT NULL,
                review_text TEXT NOT NULL
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS krisar (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                contact TEXT NOT NULL,
                message TEXT NOT NULL
            )
        ''')
        conn.commit()

def get_db_connection():
    conn = sql.connect('rental.db')
    conn.row_factory = sql.Row
    return conn

#--USER PAGE--#

@app.route('/')
def home():
    conn = get_db_connection()
    is_admin = False
    krisar_list = []

    if 'user_id' in session:
        user_role = conn.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        if user_role and user_role['role'] == 'admin':
            is_admin = True
            krisar_list = conn.execute('SELECT * FROM krisar').fetchall()

    conn.close()
    return render_template('index.html', is_admin=is_admin, krisar_list=krisar_list)

@app.route('/register', methods=['GET', 'POST'])
def sign_in():
    if request.method == 'POST':
        username = request.form['username']
        contact = request.form['contact']

        with get_db_connection() as conn:
            existing_user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
            if existing_user:
                flash('Username sudah digunakan! Silakan pilih username lain.', 'danger')
                return redirect(url_for('sign_in'))

            conn.execute('INSERT INTO users (username, contact, role) VALUES (?, ?, "user")',
                         (username, contact))
            conn.commit()
            flash('Registrasi berhasil! Silakan login.', 'success')
            return redirect(url_for('login'))

    return render_template('sign_in.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        contact = request.form['contact']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()

        if user and user['contact'] == contact:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login Berhasil!', 'success')
            return redirect(url_for('home'))
        else:
            flash('Username atau nomor salah!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Logout berhasil!', 'info')
    return redirect(url_for('home'))


@app.route('/menu')
def menu():
    conn = get_db_connection()
    category = request.args.get('category', "Semua")
    categories = conn.execute('SELECT DISTINCT category FROM products').fetchall()
    categories = [row['category'] for row in categories]

    if category == "Semua" or category == "":
        products = conn.execute('SELECT * FROM products').fetchall()
    else:
        products = conn.execute('SELECT * FROM products WHERE category = ?', (category,)).fetchall()

    is_admin = session.get('user_id') and \
               conn.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],)).fetchone()['role'] == 'admin'
    conn.close()
    return render_template('menu.html', products=products, categories=categories, category=category, is_admin=is_admin)

@app.route('/booking/<int:product_id>', methods=['GET', 'POST'])
def booking(product_id):
    if 'user_id' not in session:
        flash("Silahkan login terlebih dahulu!", 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()

    if not product:
        flash("Produk tidak ditemukan!", 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        contact = request.form['contact']
        book_date = request.form['book_date']
        return_date = request.form['return_date']
        duration = int(request.form['duration'])
        total_price = product['price'] * duration
        down_payment = total_price * 0.5  # DP 50%
        payment_method = request.form['payment_method']
        user_id = session['user_id']

        if 'payment_proof' not in request.files:
            flash('Bukti pembayaran wajib diunggah', 'danger')
            return redirect(request.url)

        file = request.files['payment_proof']
        if file.filename == '':
            flash('Tidak ada file yang dipilih!', 'danger')
            return redirect(request.url)

        # Pastikan direktori upload ada
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        conn.execute(
            'INSERT INTO bookings (user_id, product_id, contact, book_date, return_date, duration, total_price, down_payment, payment_method, payment_proof) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (user_id, product_id, contact, book_date, return_date, duration, total_price, down_payment, payment_method, file_path)
        )
        conn.commit()
        conn.close()

        flash('Booking berhasil! Tunggu konfirmasi dari admin.', 'success')
        return redirect(url_for('booking_list'))

    conn.close()
    return render_template('booking.html', product=product)

@app.route('/booking_list')
def booking_list():
    if 'user_id' not in session:
        flash('Silakan login terlebih dahulu!', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    user_role = conn.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],)).fetchone()['role']

    if user_role == 'admin':
        bookings = conn.execute('''
            SELECT bookings.id, users.username, products.name, bookings.book_date, bookings.return_date, 
                   bookings.duration, bookings.total_price, bookings.down_payment, 
                   bookings.payment_proof, bookings.status 
            FROM bookings 
            JOIN users ON bookings.user_id = users.id
            JOIN products ON bookings.product_id = products.id
        ''').fetchall()
    else:
        bookings = conn.execute('''
            SELECT bookings.id, products.name, bookings.book_date, bookings.return_date, 
                   bookings.duration, bookings.total_price, bookings.down_payment, 
                   bookings.payment_proof, bookings.status 
            FROM bookings 
            JOIN products ON bookings.product_id = products.id 
            WHERE user_id = ?
        ''', (session['user_id'],)).fetchall()

    conn.close()
    return render_template('booking_list.html', bookings=bookings, is_admin=(user_role == 'admin'))

@app.route('/update_booking_status', methods=['POST'])
def update_booking_status():
    if 'user_id' not in session:
        flash("Silahkan login terlebih dahulu!", 'danger')
        return redirect(url_for('login'))

    booking_id = request.form['booking_id']
    new_status = request.form['status']

    conn = get_db_connection()
    conn.execute('UPDATE bookings SET status = ? WHERE id = ?', (new_status, booking_id))
    conn.commit()
    conn.close()

    flash("Status booking berhasil diperbarui!", "success")
    return redirect(url_for('booking_list'))

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    conn = get_db_connection()
    product = conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    conn.close()

    if not product:
        flash('Product tidak ditemukan!', 'danger')
        return redirect(url_for('menu'))
    return render_template('product_detail.html', product=product)


@app.route('/reviews', methods=['GET', 'POST'])
def reviews():
    if request.method == 'POST':
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu!', 'danger')
            return redirect(url_for('login'))

        username = session['username']
        contact = request.form['contact']
        review_text = request.form['review_text']

        with get_db_connection() as conn:
            conn.execute('INSERT INTO reviews (username, contact, review_text) VALUES (?, ?, ?)',
                         (username, contact, review_text))
            conn.commit()
        flash('Review berhasil dikirim!', 'success')
        return redirect(url_for('reviews'))

    conn = get_db_connection()
    reviews = conn.execute('SELECT * FROM reviews').fetchall()
    conn.close()
    return render_template('reviews.html', reviews=reviews)


@app.route('/krisar', methods=['GET', 'POST'])
def krisar():
    if request.method == 'POST':
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu!', 'danger')
            return redirect(url_for('login'))

        username = session['username']
        contact = request.form['contact']
        message = request.form['message']

        with get_db_connection() as conn:
            conn.execute('INSERT INTO krisar (username, contact, message) VALUES (?, ?, ?)',
                         (username, contact, message))
            conn.commit()
        flash('Kritik dan saran berhasil dikirim!', 'success')
        return redirect(url_for('krisar'))

    conn = get_db_connection()
    krisar_list = conn.execute('SELECT * FROM krisar').fetchall()
    conn.close()
    return render_template('krisar.html', krisar=krisar_list)

@app.route('/menu/add', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        description = request.form['description']
        price = request.form['price']
        stock = request.form.get('stock', 1)  # Default stok = 1

        file = request.files['image']
        if file and file.filename:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)

            file_url = filename  # Hanya simpan nama file, tanpa path lengkap

            conn = get_db_connection()
            conn.execute('INSERT INTO products (name, category, description, price, stock, image) VALUES (?, ?, ?, ?, ?, ?)',
                         (name, category, description, price, stock, file_url))
            conn.commit()
            conn.close()

            flash('Produk berhasil ditambahkan!', 'success')
            return redirect(url_for('menu'))
        else:
            flash('Gambar produk wajib diunggah!', 'danger')

    return render_template('add.html')

@app.route('/edit_product/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    conn = get_db_connection()
    cursor = conn.cursor()

    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        description = request.form['description']
        price = request.form['price']

        file = request.files.get('img')
        if file and file.filename:
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            cursor.execute("UPDATE products SET name=?, category=?, description=?, price=?, image=? WHERE id=?",
                           (name, category, description, price, file_path, id))
        else:
            cursor.execute("UPDATE products SET name=?, category=?, description=?, price=? WHERE id=?",
                           (name, category, description, price, id))

        conn.commit()
        conn.close()
        flash('Produk berhasil diperbarui!', 'success')
        return redirect(url_for('menu'))

    cursor.execute("SELECT * FROM products WHERE id=?", (id,))
    item = cursor.fetchone()
    conn.close()
    return render_template('edit.html', product=product)

@app.route('/delete_product/<int:id>', methods=['GET', 'POST'])
def delete_product(id):
    with sql.connect('rental.db') as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM products WHERE id=?", (id,))
        conn.commit()
    flash('Produk berhasil dihapus!', 'success')
    return redirect(url_for('menu'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0')