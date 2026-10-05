# train_model.py
# ════════════════════════════════════════════════════════════════
# Run this ONCE (and again whenever you tweak the career profiles):
#     python train_model.py
# It trains the ML model and saves it to ml/career_model.joblib
# ════════════════════════════════════════════════════════════════
from ml.career_model import train_and_save
from config import MODEL_PATH

if __name__ == "__main__":
    print("Training Kalviman career model...\n")
    acc = train_and_save(MODEL_PATH, n_per_cluster=350, verbose=True)
    print(f"\nDone. You can now run:  python app.py")
