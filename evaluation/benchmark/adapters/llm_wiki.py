from .native_driver import NativeDriverAdapter


class LLMWikiAdapter(NativeDriverAdapter):
    """Runs the selected Wiki project's native ingestion and query executable.

    No Wiki implementation is guessed from the generic product name. A driver
    must return raw-document consumption, ingestion usage, and query call receipts.
    """
    name="llm_wiki"
    required_stages=("llm_wiki_native_ingestion", "wiki_index")
