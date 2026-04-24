"""Chapter 3 solution — re-exports IPC and Ticket production modules."""

from sovereign_agent.ipc.protocol import (  # noqa: F401
    CLOSE_SENTINEL_NAME,
    clear_close_sentinel,
    is_close_sentinel,
    read_and_consume,
    send_input,
    write_close_sentinel,
    write_ipc_message,
)
from sovereign_agent.ipc.watcher import IpcWatcher  # noqa: F401
from sovereign_agent.tickets.manifest import Manifest, OutputRecord  # noqa: F401
from sovereign_agent.tickets.state import (  # noqa: F401
    TERMINAL_TICKET_STATES,
    TicketResult,
    TicketState,
)
from sovereign_agent.tickets.ticket import (  # noqa: F401
    Ticket,
    create_ticket,
    list_tickets,
)
