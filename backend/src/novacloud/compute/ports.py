from typing import Protocol

from novacloud.compute.domain import NetworkAttachment, Template


class ComputeProvider(Protocol):
    def create(self, instance_id: str, organization_id: str, template: Template,
               network: NetworkAttachment | None = None) -> str:
        """Create (and start) a container; return a provider reference. Must be idempotent per instance_id."""
    def start(self, provider_ref: str) -> None: ...
    def stop(self, provider_ref: str) -> None: ...
    def delete(self, provider_ref: str) -> None: ...
    def status(self, provider_ref: str) -> str | None:
        """Return 'running' | 'stopped' | None (not found)."""
