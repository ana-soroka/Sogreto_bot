"""Utils package for Sogreto Bot"""

from .error_handling import (
    error_handler,
    global_error_handler,
    validate_user_input,
    BotError,
    PracticeNotFoundError,
    UserNotFoundError,
    DatabaseError
)

from .db import (
    get_or_create_user,
    update_user_progress,
    pause_user,
    resume_user,
    reset_user_progress,
    get_user_stats,
    delete_user_data
)

from .practices import (
    PracticesManager,
    practices_manager
)

__all__ = [
    # Error handling
    'error_handler',
    'global_error_handler',
    'validate_user_input',
    'BotError',
    'PracticeNotFoundError',
    'UserNotFoundError',
    'DatabaseError',
    # Database
    'get_or_create_user',
    'update_user_progress',
    'pause_user',
    'resume_user',
    'reset_user_progress',
    'get_user_stats',
    'delete_user_data',
    # Practices
    'PracticesManager',
    'practices_manager'
]
