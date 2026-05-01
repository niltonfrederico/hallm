"""Shared enumerations used across the hallm domain models."""

from enum import StrEnum


class WorkTypes(StrEnum):
    BOOK = "book"
    POEM = "poem"
    CHRONICLE = "chronicle"
    ARTICLE = "article"
    NEWS = "news"
    VIDEO = "video"
    AUDIO = "audio"
    NOTES = "notes"
    OTHER = "other"
