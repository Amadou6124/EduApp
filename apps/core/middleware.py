class SchoolMiddleware:
    """
    Attache l'école active à la request pour accès direct dans les templates.
    Utilisation : {{ request.school.name }}
    Doit être placé après AuthenticationMiddleware dans MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            request.school = request.user.school
        else:
            request.school = None
        return self.get_response(request)
