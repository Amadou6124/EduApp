# EduApp — Notes de projet

## Dette technique à corriger

- [ ] **Remplacer `DEMO_SCHOOL_ID` par `request.user.school`** dans `get_demo_school()` (`apps/schools/views.py`)
  → À faire quand le login custom sera construit (`apps/accounts/views.py`)

- [ ] **Remplacer `LOGIN_URL = '/admin/login/'`** par `accounts:login` dans `config/settings.py`
  → À faire quand la page de login custom sera créée
