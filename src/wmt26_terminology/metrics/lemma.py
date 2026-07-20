import stanza


class LemmaView:
    """A lemmatized rendering of a text plus bidirectional char-span mappings,
    so a match in either space can block the corresponding span in the other
    (match_accuracy's lemmatized construction)."""

    def __init__(self, text: str, words: list) -> None:
        self.to_lemma: list[tuple[int, int] | None] = [None] * len(text)
        parts: list[str] = []
        lemma_spans: list[tuple[int, int]] = []
        pos = 0
        for word in words:
            lemma = word.lemma or word.text
            span = (pos, pos + len(lemma))
            parts.append(lemma)
            lemma_spans.append(span)
            for i in range(word.start_char, word.end_char):
                self.to_lemma[i] = span
            pos += len(lemma) + 1
        self.lemma_text = " ".join(parts)
        self.to_surface: list[tuple[int, int] | None] = [None] * len(self.lemma_text)
        for word, (start, end) in zip(words, lemma_spans, strict=True):
            for i in range(start, end):
                self.to_surface[i] = (word.start_char, word.end_char)


class Lemmatizer:
    def __init__(self, lang: str) -> None:
        self._nlp = stanza.Pipeline(
            lang,
            processors="tokenize,pos,lemma",
            verbose=False,
            download_method=stanza.DownloadMethod.REUSE_RESOURCES,
        )
        self._phrase_cache: dict[str, str] = {}

    def views(self, texts: list[str]) -> list[LemmaView]:
        nonempty = [i for i, t in enumerate(texts) if t.strip()]
        processed = self._nlp.bulk_process([texts[i] for i in nonempty])
        views: list[LemmaView] = [LemmaView("", [])] * len(texts)
        for index, doc in zip(nonempty, processed, strict=True):
            views[index] = LemmaView(texts[index], [w for s in doc.sentences for w in s.words])
        return views

    def phrases(self, phrases: list[str]) -> dict[str, str]:
        """Lemmatized rendering per phrase (terms must be lemmatized too:
        pl 'deska rozdzielcza' lemmatizes to 'deska rozdzielczy')."""
        missing = sorted({p for p in phrases if p.strip() and p not in self._phrase_cache})
        for phrase, doc in zip(missing, self._nlp.bulk_process(missing), strict=True):
            self._phrase_cache[phrase] = " ".join(w.lemma or w.text for s in doc.sentences for w in s.words)
        return {p: self._phrase_cache[p] for p in phrases if p in self._phrase_cache}
