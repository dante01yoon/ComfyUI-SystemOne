from .systemone.nodes import SystemOneExtension


async def comfy_entrypoint() -> SystemOneExtension:
    return SystemOneExtension()
