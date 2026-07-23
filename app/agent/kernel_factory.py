"""
app/agent/kernel_factory.py — Builds and configures the Semantic Kernel instance.

The kernel is used to:
  1. Execute SK plugin functions when VoiceLive fires function_call events
  2. Expose tool schemas to the realtime API session config

Architecture note:
  The Azure OpenAI Realtime API handles its own LLM calls internally.
  We use SK here purely as a plugin executor — the kernel receives a
  function name + arguments from the realtime event, invokes the plugin,
  and returns the result string back to the audio session.
"""

from __future__ import annotations

import json

from semantic_kernel import Kernel
from semantic_kernel.functions import KernelArguments

# Try current import path first, fall back for older SK versions
try:
    from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
except ImportError:
    from semantic_kernel.connectors.ai.open_ai.services.azure_chat_completion import AzureChatCompletion  # type: ignore

from app.config import get_settings
from app.logging_config import get_logger
from app.plugins.escalation_plugin import EscalationPlugin
from app.plugins.faq_plugin import FaqPlugin
from app.plugins.offers_plugin import OffersPlugin
from app.plugins.order_plugin import OrderPlugin
from app.plugins.product_plugin import ProductPlugin
from app.plugins.store_plugin import StorePlugin

logger = get_logger(__name__)
_settings = get_settings()


def build_kernel() -> Kernel:
    """
    Create a Semantic Kernel instance with Azure OpenAI and all retail plugins.

    Returns a fully configured kernel ready to execute plugin functions.
    """
    kernel = Kernel()

    # Add Azure OpenAI chat service (used as fallback / for direct SK invocations)
    kernel.add_service(
        AzureChatCompletion(
            service_id="azure_openai",
            deployment_name=_settings.azure_openai_chat_deployment,
            endpoint=_settings.azure_openai_endpoint,
            api_key=_settings.azure_openai_api_key,
        )
    )

    # Register all retail plugins
    kernel.add_plugin(ProductPlugin(), plugin_name="products")
    kernel.add_plugin(OrderPlugin(), plugin_name="orders")
    kernel.add_plugin(StorePlugin(), plugin_name="stores")
    kernel.add_plugin(OffersPlugin(), plugin_name="offers")
    kernel.add_plugin(FaqPlugin(), plugin_name="faqs")
    kernel.add_plugin(EscalationPlugin(), plugin_name="escalation")

    logger.info(
        "kernel_built",
        plugins=["products", "orders", "stores", "offers", "faqs", "escalation"],
    )
    return kernel


async def invoke_plugin_function(
    kernel: Kernel,
    plugin_name: str,
    function_name: str,
    arguments: dict,
) -> str:
    """
    Invoke a specific kernel plugin function by name and return its string result.

    This is called by the VoiceLive bridge when the realtime API fires a function_call event.

    Args:
        kernel:        The configured Semantic Kernel instance.
        plugin_name:   Name of the registered plugin (e.g. "products").
        function_name: Function within the plugin (e.g. "search_products").
        arguments:     Dictionary of arguments from the function_call event.

    Returns:
        JSON string result to send back to the realtime session as function output.
    """
    try:
        func = kernel.get_function(plugin_name, function_name)
        kernel_args = KernelArguments(**arguments)
        result = await kernel.invoke(func, kernel_args)
        output = str(result)
        logger.info(
            "plugin_function_invoked",
            plugin=plugin_name,
            function=function_name,
            args=arguments,
        )
        return output
    except Exception as exc:
        logger.error(
            "plugin_function_error",
            plugin=plugin_name,
            function=function_name,
            error=str(exc),
        )
        return json.dumps({
            "error": True,
            "message": f"Sorry, I couldn't retrieve that information right now. Please try again.",
        })


def get_tool_definitions(kernel: Kernel) -> list[dict]:
    """
    Export all plugin functions as OpenAI tool definitions for the realtime session config.

    The Azure OpenAI Realtime API uses the same tool schema as the chat completions API.
    """
    tools = []
    for plugin in kernel.plugins.values():
        for func in plugin.functions.values():
            schema = func.metadata
            tool = {
                "type": "function",
                "name": f"{plugin.name}-{func.name}",
                "description": schema.description or f"{plugin.name} {func.name}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            }
            for param in schema.parameters:
                if param.name in ("self",):
                    continue
                prop: dict = {"type": "string"}
                if param.description:
                    prop["description"] = param.description

                # SK 1.44: param.type_ can be None, a string name, or a Python type
                type_val = getattr(param, "type_", None)
                if type_val is not None:
                    # Get name whether it's a type object or a string
                    if isinstance(type_val, type):
                        type_name = type_val.__name__.lower()
                    else:
                        type_name = str(type_val).lower()

                    if type_name in ("bool", "boolean"):
                        prop["type"] = "boolean"
                    elif type_name in ("int", "integer"):
                        prop["type"] = "integer"
                    elif type_name in ("float", "number"):
                        prop["type"] = "number"

                tool["parameters"]["properties"][param.name] = prop
                if param.is_required:
                    tool["parameters"]["required"].append(param.name)

            tools.append(tool)

    logger.info("tool_definitions_exported", count=len(tools))
    return tools
