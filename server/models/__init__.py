from models.conversation import Conversation  # noqa: F401
from models.message import Message  # noqa: F401
from models.todo import Todo  # noqa: F401
from models.event import Event  # noqa: F401
from models.memo import Memo  # noqa: F401
from models.agent_task import AgentTask  # noqa: F401

# Sentinel used by database.init_db to ensure all models are imported
_register_all = True
