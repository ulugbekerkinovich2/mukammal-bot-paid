from loader import dp

from .inline_cleanup import InlineCleanupMiddleware
from .update_logger import UpdateLoggerMiddleware

# UpdateLogger oldin (har update INFO bilan log qilinsin), keyin InlineCleanup.
dp.middleware.setup(UpdateLoggerMiddleware())
dp.middleware.setup(InlineCleanupMiddleware())
