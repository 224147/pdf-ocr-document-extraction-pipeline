"""Exception hierarchy for the extraction pipeline."""


class PipelineError(Exception):
    """Base class for all pipeline failures."""


class DocumentValidationError(PipelineError):
    """Raised when an uploaded file fails format or size validation."""


class ExtractionError(PipelineError):
    """Raised when a document cannot be parsed or rendered."""
