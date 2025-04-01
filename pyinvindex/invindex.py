from collections import defaultdict
from typing import Any, Iterable, Mapping, Sequence
import nltk

nltk.download("punkt")
nltk.download("punkt_tab")
nltk.download("wordnet")

def tokenize_document(document: str) -> Iterable[str]:
    wnl = nltk.WordNetLemmatizer()
    for token in nltk.word_tokenize(document):
        yield wnl.lemmatize(token)


class InvertedIndex:
    def __init__(self):
        # doc_id -> doc_text
        self.forward_text_index: dict[int, str] = {}
        # doc_id -> doc_tokens
        # TODO: optimize this - reference the text index instead of storing the tokens
        self.forward_token_index: defaultdict[int, list[str]] = defaultdict(list)

        # token -> (doc_id -> token_positions)
        self.inverted_index: defaultdict[str, dict[int, list[int]]] = defaultdict(
            lambda: defaultdict(list)
        )

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the inverted index to a dictionary for JSON serialization.

        :return: A dictionary representation of the inverted index.
        """
        return {
            "forward_text_index": self.forward_text_index,
            "forward_token_index": self.forward_token_index,
            "inverted_index": self.inverted_index,
        }

    def load_dict(self, data: dict[str, Any]):
        """
        Load the inverted index from a dictionary.

        :param data: The dictionary containing the inverted index.
        """
        self.forward_text_index = data["forward_text_index"]
        self.forward_token_index = data["forward_token_index"]

        self.inverted_index.clear()
        self.inverted_index.update(data["inverted_index"])

    def add_document(self, doc_id: int, doc: str):
        """
        Insert a document into the index.

        :param doc_id: The document ID.
        :param doc: The document text.
        """
        if doc_id in self.forward_text_index or doc_id in self.forward_token_index:
            raise ValueError(f"Document ID {doc_id} already exists in the index.")

        self.forward_text_index[doc_id] = doc

        for token_index, token in enumerate(tokenize_document(doc)):
            self.forward_token_index[doc_id].append(token)
            self.inverted_index[token][doc_id].append(token_index)

    def get_docs_for_token(self, token: str) -> Mapping[int, list[int]]:
        """
        Get the document IDs and document token indices for a given token.

        :param token: The token to look up.
        :return: A mapping of doc_id to list[token_index] for each document containing the token.
        """
        return self.inverted_index.get(token, {})

    def get_tokens_for_doc(self, doc_id: int) -> Sequence[str]:
        """
        Get the tokens for a given document ID.

        :param doc_id: The document ID.
        :return: A list of tokens for the document.
        """
        return self.forward_token_index.get(doc_id, [])

    def search_index(self, text: str) -> list[tuple[int, list[int]]]:
        """
        Search the index for a given text.

        :param text: The text to search for.
        :return: A list of tuples (doc_id, tokens) sorted by total matching token count in descending order.
        """
        doc_ids: defaultdict[int, list[tuple[str, list[int]]]] = defaultdict(list)

        for token in tokenize_document(text):
            for doc_id, token_indices in self.get_docs_for_token(token).items():
                doc_ids[doc_id].append((token, token_indices))

        # sort by total matching token count
        return sorted(
            doc_ids.items(),
            key=lambda item: sum(len(ti[1]) for ti in item[1]),
            reverse=True,
        )

    def __contains__(self, token: str) -> bool:
        return token in self.inverted_index

    def __getitem__(self, token: str) -> list[tuple[int, list[int]]]:
        return list(self.get_docs_for_token(token))
