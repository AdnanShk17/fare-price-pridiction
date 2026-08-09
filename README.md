<<<<<<< HEAD
# 🚕 Mumbai Smart Cab Fare Prediction & Route Optimization System

An advanced Machine Learning and Geospatial Routing system that predicts cab fares across Mumbai, finds shortest driving routes via **OSRM (Open Source Routing Machine)** on **OpenStreetMap**, and compares estimated fares across **Ola**, **Uber**, **Rapido**, and **RTO Kaali-Peeli meter rates**.

---

## 📌 Features & Key Modules

- 📍 **Mumbai-Specific Dataset & Model:** Trained on 5,000 Mumbai trips with INR (₹) fares, Mumbai coordinates (18.89°N - 19.30°N, 72.75°E - 73.05°E), RTO minimum tariffs, and weather/traffic multipliers.
- 🗺️ **OSRM Shortest Driving Route Integration:** Connects to OSRM driving route API for real road paths, exact road distance (KM), and traffic-adjusted travel duration (Mins).
- 🎨 **Multi-Provider Interactive Map:** Select between OpenStreetMap Standard, CartoDB Positron, CartoDB Dark Matter, and Esri World Street Map tiles powered by PyDeck.
- 📊 **Multi-Platform Fare Comparison Engine:** Side-by-side estimated price comparison cards and bar charts comparing:
  - 🎯 **Our Random Forest ML Model Prediction**
  - 🟡 **Ola Mini / Go**
  - ⬛ **Uber Go**
  - 🛵 **Rapido Bike / Auto**
  - 🚕 **Official RTO Kaali-Peeli Meter Fare**
- 📚 **College Project Guide & Viva Documentation Tab:** Embedded 8-point academic report & FAQ answers explaining model accuracy, dataset engineering, Dijkstra vs. A* vs. OSRM Multi-Level Dijkstra routing algorithms.

---

## 📂 Project Structure

```
NYC-Smart-Cab-Fare-Prediction/
├── train_mumbai_model.py     # Script to generate Mumbai dataset & train ML model
├── mumbai_cab_fare_train.csv  # 5,000 record Mumbai cab trip dataset (in ₹)
├── mumbai_cab_fare_model.pkl  # Trained Random Forest Regressor model file
├── mumbai_model_metrics.json  # Model evaluation metrics (MAE, RMSE, R² Score)
├── route_engine.py           # OSRM API integration client & routing algorithm analyzer
├── platform_fares.json       # Configurable pricing rules for Ola, Uber, Rapido
├── mumbai_app.py             # Streamlit interactive web application dashboard
├── CFP.py                    # Legacy NYC app script
├── requirements.txt          # Python dependencies
└── README.md                 # Project documentation
```

---

## ▶️ How To Run

### 1️⃣ Train the Model (Optional / Pre-built)
```bash
python train_mumbai_model.py
```

### 2️⃣ Run the Streamlit Application
```bash
streamlit run mumbai_app.py
```

---

## 🧠 Technical Stack & Free-Tier Architecture

- **Frontend / Dashboard:** Streamlit, PyDeck, Pandas, NumPy
- **Routing Engine:** Open Source Routing Machine (OSRM API) over OpenStreetMap data
- **Machine Learning:** Scikit-Learn (Random Forest Regressor), Joblib
- **Map Tiles:** OpenStreetMap, CartoDB, Esri (100% Free Tier, No Paid API Keys required)

---

## 🎓 Academic Guide Reporting Points

1. **Problem Statement:** Mumbai-specific cab fare prediction & platform comparison.
2. **Why Mumbai Data:** Replaced NYC grid/USD system with Mumbai RTO regulations (₹28 base), monsoon multipliers, and suburban arterial road networks.
3. **Shortest Route Logic:** OSRM Multi-Level Dijkstra (MLD) / Contraction Hierarchies (CH) vs. conceptual Dijkstra & A* algorithms.
4. **Platform Comparison:** Rule-based calculation from `platform_fares.json` allowing offline/free platform comparisons without live web scraping risks.
=======
# fare-price-pridiction
building a project of fair price pridiction using stramlit and others
>>>>>>> 27839d28874e23ed9315fd3d30c64f241c852f54
