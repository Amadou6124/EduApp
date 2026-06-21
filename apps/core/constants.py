"""Seuils métier centralisés — évite les nombres magiques dispersés."""

# ── Seuils pédagogiques ──────────────────────────────────────────────
PASS_THRESHOLD = 10           # Moyenne minimale pour passer
GOOD_AVERAGE_THRESHOLD = 12   # Moyenne "bonne classe" (dashboard)
MASTERY_THRESHOLD = 80        # % maîtrise → "terminé fort"
MASTERY_WEAK_THRESHOLD = 40   # % maîtrise → "terminé faible" (= valeur actuelle du code)

# ── Seuils financiers (taux de recouvrement) ─────────────────────────
PAYMENT_GOOD_THRESHOLD = 80      # bon
PAYMENT_ALERT_THRESHOLD = 60     # alerte
PAYMENT_CRITICAL_THRESHOLD = 40  # critique
