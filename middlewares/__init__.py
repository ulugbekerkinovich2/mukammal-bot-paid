from loader import dp

from .inline_cleanup import InlineCleanupMiddleware

dp.middleware.setup(InlineCleanupMiddleware())
