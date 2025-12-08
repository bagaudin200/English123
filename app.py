"""
English School - Single-file Flask web app

This is a sandbox-friendly, robust version that avoids using Werkzeug's threaded dev server when that leads
to SystemExit in restricted environments. Instead it will prefer the standard library WSGI server (wsgiref)
when started via the CLI `run` command. By default the script will NOT start a server to avoid accidental
SystemExit in sandboxes.

Features:
- Bright, responsive frontend (HTML/CSS/JS embedded)
- Plans: Group (590 ₽/hour), Individual (790 ₽/hour)
- Booking form (stores to SQLite)
- Price calculator for selected plan and hours
- Admin view to list bookings (simple, password-protected demo)

Usage:
- Run server locally: python english_school_flask_app.py run [--host HOST] [--port PORT]
- Run tests: python english_school_flask_app.py test
- No args: prints help and does NOT start the server (safe for restricted environments)

Notes:
- This file intentionally avoids Flask's debugger/reloader and Werkzeug development server when possible
  because some environments raise SystemExit / import errors (e.g. missing _multiprocessing) when using
  those features.
- For production deploy, run under a proper WSGI server (gunicorn/uvicorn/waitress) and secure /admin.
"""

from flask import Flask, request, g, redirect, url_for, render_template_string, flash, abort
import sqlite3
import os
import sys
import argparse
from datetime import datetime

DATABASE = 'bookings.db'
GROUP_PRICE = 590  # ₽ per hour
INDIVIDUAL_PRICE = 790  # ₽ per hour

app = Flask(__name__)
app.secret_key = 'replace-with-a-secure-random-key'
app.debug = False  # keep debug off to avoid auto-reloader

# ---------- Utility functions & tests ----------

def calculate_price(plan: str, hours: int) -> int:
    """Return total price in rubles for given plan and hours."""
    prices = {'group': GROUP_PRICE, 'individual': INDIVIDUAL_PRICE}
    return prices.get(plan, GROUP_PRICE) * max(1, int(hours))


def _run_unit_tests():
    # Basic unit tests for core logic
    print('Running unit tests...')
    assert calculate_price('group', 1) == 590
    assert calculate_price('individual', 1) == 790
    assert calculate_price('group', 8) == 590 * 8
    assert calculate_price('individual', 16) == 790 * 16
    # Template placeholder tests
    sample = 'Price is %%GROUP_PRICE%% and %%INDIVIDUAL_PRICE%%'
    replaced = sample.replace('%%GROUP_PRICE%%', str(GROUP_PRICE)).replace('%%INDIVIDUAL_PRICE%%', str(INDIVIDUAL_PRICE))
    assert '%%' not in replaced
    print('All tests passed.')


# ---------- Database helpers ----------

def get_db():
    """Return a sqlite3 connection stored on the Flask g object."""
    db = getattr(g, '_database', None)
    if db is None:
        need_init = not os.path.exists(DATABASE)
        # Use check_same_thread=False to allow access from different threads if WSGI server is threaded
        db = g._database = sqlite3.connect(DATABASE, check_same_thread=False)
        if need_init:
            init_db(db)
    return db


def init_db(db):
    cur = db.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        email TEXT,
        phone TEXT,
        plan TEXT,
        hours INTEGER,
        price INTEGER,
        notes TEXT,
        created_at TEXT
    )
    ''')
    db.commit()


@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()


# ---------- Templates (single-file) ----------
BASE_HTML = '''
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bright English School — Учись с удовольствием</title>
  <style>
    /* Simple bright theme */
    :root{--brand:#FF6B6B;--accent:#FFD93D;--muted:#6C757D;--bg:#FFF7E6}
    *{box-sizing:border-box}
    body{font-family:Inter, system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial; margin:0; background:linear-gradient(180deg, #fff 0%, var(--bg) 100%); color:#111}
    .container{max-width:1100px;margin:0 auto;padding:28px}
    header{display:flex;align-items:center;justify-content:space-between;padding:12px 0}
    .logo{display:flex;align-items:center;gap:12px}
    .logo .icon{width:56px;height:56px;background:var(--brand);border-radius:12px;display:flex;align-items:center;justify-content:center;color:white;font-weight:700;font-size:20px}
    nav a{margin-left:14px;text-decoration:none;color:var(--muted)}
    .hero{display:grid;grid-template-columns:1fr 420px;gap:28px;align-items:center;margin-top:18px}
    .card{background:white;border-radius:18px;padding:20px;box-shadow:0 8px 30px rgba(18,18,18,0.06)}
    h1{margin:0 0 8px;font-size:32px}
    p.lead{margin:0 0 18px;color:var(--muted)}
    .cta{display:inline-block;background:var(--brand);color:white;padding:12px 18px;border-radius:12px;text-decoration:none;font-weight:600}
    .plans{display:flex;gap:14px;margin-top:18px}
    .plan{flex:1;padding:16px;border-radius:12px}
    .plan h3{margin:6px 0}
    .price{font-size:22px;font-weight:700}
    .muted{color:var(--muted)}
    form .row{display:flex;gap:8px}
    input,select,textarea{width:100%;padding:10px;border-radius:8px;border:1px solid #eee;font-size:14px}
    .bright{background:linear-gradient(90deg,var(--accent),#fff);padding:12px;border-radius:12px}
    footer{margin-top:28px;padding:18px;text-align:center;color:var(--muted)}

    @media (max-width:900px){
      .hero{grid-template-columns:1fr;}
      .logo .icon{width:46px;height:46px}
    }
  </style>
  <script>
    function calcPrice(){
      const planElem = document.getElementById('plan');
      const hoursElem = document.getElementById('hours');
      if(!planElem || !hoursElem) return;
      const plan = planElem.value;
      let hours = parseInt(hoursElem.value) || 1;
      if(hours < 1) hours = 1;
      const prices = { 'group': %%GROUP_PRICE%%, 'individual': %%INDIVIDUAL_PRICE%% };
      const price = prices[plan] * hours;
      const total = document.getElementById('total');
      if(total) total.innerText = price.toLocaleString('ru-RU') + ' ₽';
    }
    document.addEventListener('DOMContentLoaded', ()=>{
      const el = document.getElementById('hours');
      if(el) el.addEventListener('input', calcPrice);
      const pl = document.getElementById('plan');
      if(pl) pl.addEventListener('change', calcPrice);
      calcPrice();
    });
  </script>
</head>
<body>
  <div class="container">
    <header>
      <div class="logo">
        <div class="icon">ES</div>
        <div>
          <div style="font-weight:800">Bright English School</div>
          <div class="muted" style="font-size:13px">Учите английский с радостью — дети и взрослые</div>
        </div>
      </div>
      <nav>
        <a href="/">Главная</a>
        <a href="/plans">Тарифы</a>
        <a href="/book">Запись</a>
        <a href="/admin">Админ</a>
      </nav>
    </header>

    %%CONTENT%%

    <footer>
      © Bright English School — все права защищены • Сделано с любовью
    </footer>
  </div>
</body>
</html>
'''

HOME_SECTION = '''
<div class="hero">
  <div>
    <div class="card">
      <h1>Английский, который хочется учить</h1>
      <p class="lead">Яркие занятия для взрослых и детей: живые учителя, разговорная практика, подготовка к экзаменам и дружелюбная атмосфера.</p>
      <div class="plans">
        <div class="plan card" style="border:3px solid rgba(255,107,107,0.12)">
          <h3>Групповые занятия</h3>
          <div class="price">%%GROUP_PRICE%% ₽ / час</div>
          <div class="muted">Идеально для тех, кто любит компанию и экономит</div>
          <div style="margin-top:10px"><a class="cta" href="/book?plan=group">Записаться</a></div>
        </div>
        <div class="plan card" style="border:3px solid rgba(255,217,61,0.12)">
          <h3>Индивидуально</h3>
          <div class="price">%%INDIVIDUAL_PRICE%% ₽ / час</div>
          <div class="muted">Максимальная эффективность — индивидуальная программа</div>
          <div style="margin-top:10px"><a class="cta" href="/book?plan=individual">Записаться</a></div>
        </div>
      </div>
    </div>

    <div style="margin-top:14px;display:flex;gap:12px;">
      <div class="card bright" style="flex:1">
        <strong>Новый набор для детей</strong>
        <p class="muted">Весёлые уроки с играми и песнями — 4-10 лет.</p>
      </div>
      <div class="card bright" style="flex:1">
        <strong>Онлайн и вживую</strong>
        <p class="muted">Удобные форматы: Zoom или наши классы.</p>
      </div>
    </div>
  </div>

  <div class="card">
    <h3>Быстрый калькулятор стоимости</h3>
    <form method="GET" action="/book" onsubmit="return true;">
      <div style="margin-bottom:10px">
        <label>План</label>
        <select id="plan" name="plan">
          <option value="group">Групповой</option>
          <option value="individual">Индивидуальный</option>
        </select>
      </div>
      <div style="margin-bottom:10px">
        <label>Часов</label>
        <input id="hours" name="hours" type="number" min="1" value="1">
      </div>
      <div style="margin-bottom:10px">
        <strong>Итого: <span id="total">—</span></strong>
      </div>
      <div>
        <button class="cta" type="submit">Перейти к записи</button>
      </div>
    </form>
  </div>
</div>
'''

PLANS_SECTION = '''
<div class="card">
  <h2>Тарифы и пакеты</h2>
  <p class="muted">Все цены указаны в российских рублях (₽).</p>
  <div style="display:flex;gap:12px;margin-top:12px;flex-wrap:wrap">
    <div class="card" style="flex:1;min-width:260px">
      <h3>Групповой</h3>
      <div class="price">%%GROUP_PRICE%% ₽ / час</div>
      <p class="muted">Занятия в группе до 8 человек.</p>
      <ul>
        <li>Разговорная практика</li>
        <li>Домашние задания</li>
        <li>Гибкий график</li>
      </ul>
      <a class="cta" href="/book?plan=group">Записаться</a>
    </div>
    <div class="card" style="flex:1;min-width:260px">
      <h3>Индивидуально</h3>
      <div class="price">%%INDIVIDUAL_PRICE%% ₽ / час</div>
      <p class="muted">Персональная программа и максимум внимания от преподавателя.</p>
      <ul>
        <li>Подготовка к экзаменам</li>
        <li>Коррекция произношения</li>
        <li>Индивидуальные материалы</li>
      </ul>
      <a class="cta" href="/book?plan=individual">Записаться</a>
    </div>
  </div>

  <div style="margin-top:14px">
    <h4>Пакеты (пример)</h4>
    <p>Экономный — 8 групповых уроков: <strong>%%GROUP_8%% ₽</strong> (590 × 8)</p>
    <p>Интенсив — 16 индивидуальных уроков: <strong>%%INDIV_16%% ₽</strong> (790 × 16)</p>
  </div>
</div>
'''

BOOK_SECTION = '''
<div class="card">
  <h2>Запись на урок</h2>
  {% with messages = get_flashed_messages() %}
    {% if messages %}
      <div style="margin-bottom:8px;color:green">{{ messages[0] }}</div>
    {% endif %}
  {% endwith %}
  <form method="POST" action="/book">
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
      <div>
        <label>Имя</label>
        <input name="name" required>
      </div>
      <div>
        <label>Эл. почта</label>
        <input type="email" name="email" required>
      </div>
      <div>
        <label>Телефон</label>
        <input name="phone">
      </div>
      <div>
        <label>План</label>
        <select id="plan" name="plan">
          <option value="group" {% if plan=='group' %}selected{% endif %}>Групповой</option>
          <option value="individual" {% if plan=='individual' %}selected{% endif %}>Индивидуальный</option>
        </select>
      </div>
      <div>
        <label>Часов (количество)</label>
        <input id="hours" name="hours" type="number" min="1" value="1">
      </div>
      <div>
        <label>Комментарии</label>
        <input name="notes">
      </div>
    </div>

    <div style="margin-top:12px">
      <strong>Итого: <span id="total">—</span></strong>
    </div>

    <div style="margin-top:12px;display:flex;gap:8px">
      <button class="cta" type="submit">Отправить запись</button>
      <a href="/" style="align-self:center;color:var(--muted);text-decoration:none">Назад</a>
    </div>
  </form>

  <script>calcPrice();</script>
</div>
'''

ADMIN_SECTION = '''
<div class="card">
  <h2>Админ — записи</h2>
  <p class="muted">Демо-страница — реализуйте авторизацию для реального использования.</p>
  {% if bookings|length == 0 %}
    <p>Записей нет.</p>
  {% else %}
    <table style="width:100%;border-collapse:collapse">
      <thead>
        <tr style="text-align:left;border-bottom:1px solid #eee">
          <th>#</th><th>Имя</th><th>План</th><th>Часов</th><th>Цена</th><th>Контакты</th><th>Дата</th>
        </tr>
      </thead>
      <tbody>
        {% for b in bookings %}
        <tr style="border-bottom:1px solid #f6f6f6">
          <td>{{ b['id'] }}</td>
          <td>{{ b['name'] }}</td>
          <td>{{ b['plan'] }}</td>
          <td>{{ b['hours'] }}</td>
          <td>{{ b['price'] }} ₽</td>
          <td>{{ b['email'] }} / {{ b['phone'] }}</td>
          <td>{{ b['created_at'] }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  {% endif %}
</div>
'''

# Replace placeholders with actual numbers (as plain integers) to avoid Python % formatting issues
BASE_HTML = BASE_HTML.replace('%%GROUP_PRICE%%', str(GROUP_PRICE)).replace('%%INDIVIDUAL_PRICE%%', str(INDIVIDUAL_PRICE))
HOME_SECTION = HOME_SECTION.replace('%%GROUP_PRICE%%', str(GROUP_PRICE)).replace('%%INDIVIDUAL_PRICE%%', str(INDIVIDUAL_PRICE))
PLANS_SECTION = PLANS_SECTION.replace('%%GROUP_PRICE%%', str(GROUP_PRICE)).replace('%%INDIVIDUAL_PRICE%%', str(INDIVIDUAL_PRICE)).replace('%%GROUP_8%%', str(GROUP_PRICE*8)).replace('%%INDIV_16%%', str(INDIVIDUAL_PRICE*16))

# ---------- Routes ----------
@app.route('/')
def home():
    html = BASE_HTML.replace('%%CONTENT%%', HOME_SECTION)
    return render_template_string(html)


@app.route('/plans')
def plans():
    html = BASE_HTML.replace('%%CONTENT%%', PLANS_SECTION)
    return render_template_string(html)


@app.route('/book', methods=['GET', 'POST'])
def book():
    db = get_db()
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        plan = request.form.get('plan')
        try:
            hours = int(request.form.get('hours') or 1)
        except ValueError:
            hours = 1
        price = calculate_price(plan, hours)
        notes = request.form.get('notes')
        cur = db.cursor()
        cur.execute('INSERT INTO bookings (name,email,phone,plan,hours,price,notes,created_at) VALUES (?,?,?,?,?,?,?,?)',
                    (name, email, phone, plan, hours, price, notes, datetime.utcnow().isoformat()))
        db.commit()
        flash('Запись успешно создана! Мы свяжемся с вами в ближайшее время.')
        return redirect(url_for('book'))

    # GET
    plan = request.args.get('plan', 'group')
    hours = request.args.get('hours', '1')
    html = BASE_HTML.replace('%%CONTENT%%', BOOK_SECTION)
    return render_template_string(html, plan=plan, hours=hours)


@app.route('/admin')
def admin():
    # Simple password protection for demo purposes
    pw = request.args.get('pw')
    if pw != 'demo-password':
        return abort(401, 'Unauthorized — add ?pw=demo-password to view admin (demo only)')
    db = get_db()
    cur = db.cursor()
    cur.execute('SELECT id,name,email,phone,plan,hours,price,notes,created_at FROM bookings ORDER BY id DESC')
    rows = cur.fetchall()
    bookings = []
    for r in rows:
        bookings.append({
            'id': r[0], 'name': r[1], 'email': r[2], 'phone': r[3], 'plan': r[4], 'hours': r[5], 'price': r[6], 'notes': r[7], 'created_at': r[8]
        })
    html = BASE_HTML.replace('%%CONTENT%%', ADMIN_SECTION)
    return render_template_string(html, bookings=bookings)


# ---------- Server runner ----------
def run_server(host='127.0.0.1', port=5000):
    """Start a simple WSGI server using the standard library. Catch SystemExit/OSError and show diagnostics."""
    from wsgiref.simple_server import make_server, WSGIRequestHandler

    class QuietHandler(WSGIRequestHandler):
        # reduce logging noise - override log_message
        def log_message(self, format, *args):
            pass

    try:
        print(f'Starting server on http://{host}:{port} (wsgiref)')
        httpd = make_server(host, port, app, handler_class=QuietHandler)
        httpd.serve_forever()
    except SystemExit as e:
        print('SystemExit caught while starting server:', e)
        print('This environment may not allow starting a development server. Use a proper WSGI server for production.')
    except OSError as e:
        print('OSError when attempting to bind or start server:', e)
        print('Maybe the port is in use or binding is restricted in this environment.')
    except Exception as e:
        print('Unexpected error while starting server:', repr(e))


def print_help():
    print('\nUsage: python english_school_flask_app.py [run|test]\n')
    print('  run  - start the WSGI server (wsgiref) if your environment allows it')
    print('  test - run unit tests')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='English School Flask App runner')
    parser.add_argument('cmd', nargs='?', help='run or test')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=5000)
    args = parser.parse_args()

    # Ensure DB exists before tests or run
    with app.app_context():
        get_db()

    if not args.cmd:
        print_help()

    else:
        if args.cmd == 'test':
            _run_unit_tests()
        elif args.cmd == 'run':
            run_server(host=args.host, port=args.port)
        else:
            print('Unknown command:', args.cmd)
            print_help()

