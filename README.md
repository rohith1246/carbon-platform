# CarbonWise 🌿

A **production-ready Carbon Footprint Awareness Platform** built with Flask, SQLite, and Groq LLM.

Track your daily CO₂ emissions from travel, food, and electricity — then receive personalised AI-powered reduction strategies.

---

## ✨ Features

| Feature | Description |
|---|---|
| **Auth** | Register / Login / Logout with Werkzeug password hashing |
| **Activity Logging** | Car, bike, bus, flight, veg/non-veg meals, electricity |
| **Carbon Engine** | Deterministic CO₂ calculation (science-backed emission factors) |
| **AI Insights** | Groq LLM returns structured JSON: summary, tips, eco-score |
| **Dashboard** | Daily score, AI insights panel, recent activity table |
| **Analytics** | Weekly totals, category bar chart, daily trend, tips |
| **Testing** | Comprehensive Pytest suite (30+ assertions) |
| **Deployment** | Render-ready via Gunicorn + Procfile |

---

## 🚀 Local Setup

### 1. Clone & enter directory
```bash
git clone <repo-url>
cd carbon-platform
```

### 2. Create virtual environment
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure environment variables
```bash
cp .env.example .env
# Edit .env and set GROQ_API_KEY and SECRET_KEY
```

### 5. Run the app
```bash
python app.py
# Open http://localhost:5000
```

---

## 🧪 Running Tests

```bash
pytest tests/test_app.py -v
```

All 5 test classes must pass:
1. `TestCarbonCalculation` – emission factor accuracy
2. `TestApiResponse` – Flask route status codes
3. `TestAiJsonStructure` – JSON schema validation
4. `TestLogin` – full auth flow
5. `TestInputValidation` – bad input rejection

---

## ⚙️ Emission Factors

| Activity | Factor |
|---|---|
| Car | 0.21 kg CO₂ / km |
| Motorbike | 0.05 kg CO₂ / km |
| Bus | 0.08 kg CO₂ / km |
| Flight | 0.255 kg CO₂ / km |
| Non-veg meal | 2.5 kg CO₂ / meal |
| Veg meal | 0.5 kg CO₂ / meal |
| Electricity | 0.82 kg CO₂ / kWh |

---

## 🌐 Deploy to Render

1. Push this repo to GitHub.
2. Create a **new Web Service** on [render.com](https://render.com).
3. Set **Build Command**: `pip install -r requirements.txt`
4. Set **Start Command**: `gunicorn app:app`
5. Add **Environment Variables**:
   - `GROQ_API_KEY` → your key from [console.groq.com](https://console.groq.com)
   - `SECRET_KEY` → a long random string

> **Note**: SQLite persists to the local disk on Render's free tier. For production persistence use Render's **Persistent Disk** add-on.

---

## 📁 Project Structure

```
carbon-platform/
├── app.py              ← Flask app + routes
├── auth.py             ← Registration, login, session logic
├── carbon_engine.py    ← CO₂ calculation + DB aggregation
├── ai_engine.py        ← Groq LLM integration
├── requirements.txt
├── Procfile
├── .env.example
├── templates/
│   ├── index.html      ← Landing page
│   ├── login.html
│   ├── register.html
│   ├── dashboard.html  ← Main app screen
│   └── analytics.html  ← Weekly analytics
├── static/
│   └── style.css       ← Full design system (dark glass)
└── tests/
    └── test_app.py     ← Pytest test suite
```

---

## 🔒 Security Notes

- Passwords hashed with `werkzeug.security.generate_password_hash` (PBKDF2-SHA256)
- All SQL queries use parameterized statements (no string interpolation)
- Session secrets loaded from environment variables
- Input validated server-side on every route

---

## 📄 License

MIT — free to use, modify, and deploy.
