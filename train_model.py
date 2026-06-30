from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

ROOT = Path(__file__).parent
CSV_PATH = ROOT / "motor_fault_data.csv"
MODEL_PATH = ROOT / "rf_model.pkl"


def main():
    df = pd.read_csv(CSV_PATH)
    features = ["temperature_C", "vib_rms_g"]
    X = df[features]
    y = df["label"].astype(int)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    clf = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_leaf=4,
        random_state=42,
        n_jobs=-1,
    )
    clf.fit(X_train, y_train)
    pred = clf.predict(X_test)
    print(classification_report(y_test, pred, target_names=["NORMAL", "CRITICAL"]))
    joblib.dump({"model": clf, "features": features}, MODEL_PATH)
    print(f"Saved {MODEL_PATH}")


if __name__ == "__main__":
    main()
