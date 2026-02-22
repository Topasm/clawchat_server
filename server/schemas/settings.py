from pydantic import BaseModel


class SettingsPayload(BaseModel):
    # All fields optional so partial updates work
    fontSize: int | None = None
    messageBubbleStyle: str | None = None
    sendOnEnter: bool | None = None
    showTimestamps: bool | None = None
    showAvatars: bool | None = None
    llmModel: str | None = None
    temperature: float | None = None
    systemPrompt: str | None = None
    maxTokens: int | None = None
    streamResponses: bool | None = None
    theme: str | None = None
    compactMode: bool | None = None
    sidebarSize: float | None = None
    chatPanelSize: float | None = None
    notificationsEnabled: bool | None = None
    reminderSound: bool | None = None
    saveHistory: bool | None = None
    analyticsEnabled: bool | None = None


class SettingsResponse(BaseModel):
    settings: dict  # The full settings object
    updated_at: str
