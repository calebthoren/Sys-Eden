from datetime import UTC, datetime, timedelta

from sys_eden.cli_design import (
    ConversationPreview,
    HomeView,
    MonitoringPreview,
    render_help,
    render_home,
    render_non_stoppable_warning,
)
from sys_eden.client_sessions import ClientSessionRegistry
from sys_eden.conversation_models import ConversationRole
from sys_eden.conversation_repository import ConversationRepository
from sys_eden.conversation_service import ConversationService
from sys_eden.core_application import CoreLifecycleState
from sys_eden.report_repository import ReportRepository
from sys_eden.storage import Database
from sys_eden.task_models import InterruptionMode, TechnicalOperation


class FakeClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 25, tzinfo=UTC)

    def now(self) -> datetime:
        return self.value

    def monotonic(self) -> float:
        return 0


def test_help_names_modifier_compatibility_and_uses_new_core_commands():
    rendered = render_help()
    assert "/corestart" in rendered
    assert "/corestop" in rendered
    assert "/shutdown" not in rendered
    assert "Works with: chat, inspect" in rendered
    assert "--json" in rendered


def test_stopped_home_has_no_chat_bar_and_only_safe_client_choices():
    rendered = render_home(HomeView(core_state=CoreLifecycleState.STOPPED))
    assert rendered == "Eden Core: stopped"
    assert "New Chat" not in rendered


def test_running_home_keeps_conversation_activity_out_of_the_status_summary():
    conversations = [
        ConversationPreview(id=f"TMP-{index}", title=f"Chat {index}", activity="working")
        for index in range(6)
    ]
    monitoring = [
        MonitoringPreview(id=f"TSK-{index}", title=f"Watch {index}") for index in range(6)
    ]
    rendered = render_home(
        HomeView(
            core_state=CoreLifecycleState.RUNNING,
            active_conversations=conversations,
            monitoring_tasks=monitoring,
        )
    )
    assert "TMP-4" not in rendered
    assert "Active conversations" not in rendered
    assert "[See all 6]" in rendered
    assert "temporary conversations remain" in rendered


def test_non_stoppable_warning_is_bold_or_explicit_in_no_ansi_mode():
    operation = TechnicalOperation(
        kind="bounded_provider_call",
        summary="Wait for provider completion.",
        interruption_mode=InterruptionMode.SAFE_BOUNDARY_ONLY,
        non_stoppable_reason="Interrupting this call could leave its result uncertain.",
    )
    assert "\x1b[1m" in (render_non_stoppable_warning(operation) or "")
    plain = render_non_stoppable_warning(operation, ansi=False)
    assert plain is not None
    assert plain.startswith("!!! WARNING")
    assert "next safe boundary" in plain


def test_vanished_client_cleanup_is_scoped_to_its_temporary_chats(tmp_path):
    database = Database(tmp_path / "eden.db")
    database.initialize()
    clock = FakeClock()
    conversations = ConversationService(
        ConversationRepository(database), ReportRepository(database), clock=clock
    )
    clients = ClientSessionRegistry(
        conversations, clock=clock, disconnect_grace=timedelta(seconds=5)
    )
    first = clients.connect()
    second = clients.connect()
    first_chat = conversations.create_temporary(title="First", owner_client_id=first.id)
    second_chat = conversations.create_temporary(title="Second", owner_client_id=second.id)
    conversations.append(
        first_chat.conversation.id, role=ConversationRole.USER, content="Keep while connected."
    )
    conversations.set_temporary_working(first_chat.conversation.id, working=True)

    assessment = clients.assess_close(first.id)
    assert assessment.requires_warning
    assert assessment.active_temporary_ids == [first_chat.conversation.id]
    clients.disconnect(first.id)
    clock.value += timedelta(seconds=6)

    expired = clients.expire_disconnected()
    assert expired[first.id] == [first_chat.conversation.id]
    assert conversations.temporary_for_client(first.id) == []
    assert (
        conversations.temporary_for_client(second.id)[0].conversation.id
        == second_chat.conversation.id
    )
    database.close()


def test_missing_heartbeat_expires_vanished_client_without_explicit_disconnect(tmp_path):
    database = Database(tmp_path / "eden.db")
    database.initialize()
    clock = FakeClock()
    conversations = ConversationService(
        ConversationRepository(database), ReportRepository(database), clock=clock
    )
    clients = ClientSessionRegistry(
        conversations,
        clock=clock,
        lease_timeout=timedelta(seconds=5),
        disconnect_grace=timedelta(seconds=3),
    )
    client = clients.connect()
    chat = conversations.create_temporary(title="Vanished", owner_client_id=client.id)
    conversations.set_temporary_working(chat.conversation.id, working=True)

    clock.value += timedelta(seconds=9)

    assert clients.expire_disconnected()[client.id] == [chat.conversation.id]
    assert conversations.temporary_for_client(client.id) == []
    database.close()
