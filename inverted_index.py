from textblob import TextBlob
import re
import os
import re
import math
import nltk

from nltk.corpus import stopwords
from nltk.stem.porter import PorterStemmer
from nltk.tokenize import word_tokenize

stemmer = PorterStemmer()
stop_words = set((stopwords.words("english")) + [",", ":"])


k1 = 0.5
b = 1


def normalise_query(query):
    query = clean_line(query)
    tokens = word_tokenize(query.lower())
    filtered_tokens = [
        stemmer.stem(token) for token in tokens if token not in stop_words
    ]
    return " ".join(filtered_tokens)


def clean_line(line):
    line = re.sub(r"[_.]{2,}", "", line)
    line = re.sub(r"[\"]", "", line)
    line = re.sub(r"\w *\)", "", line)
    line = re.sub(r"^\d *\.", "", line)
    return line


def make_comparator(less_than):
    def compare(x, y):
        if less_than(x, y):
            return -1
        elif less_than(y, x):
            return 1
        else:
            return 0

    return compare


class Document:
    def __init__(self, map_of_terms, docId):
        self.docId = docId
        self.map_of_terms = map_of_terms
        self.numberOfTerms = len(self.map_of_terms)


class Reader:
    def __init__(self, path, original_files_dir):
        self.path = path
        self.original_files_dir = original_files_dir
        # add trailing / in original_files_dir

        if self.original_files_dir[-1] != "/":
            self.original_files_dir += "/"
        self.file_names = self.get_file_names()
        self.current_file_index = 0

    def get_file_names(self):
        # return sorted order
        return sorted(os.listdir(self.path))

    def get_original_passage_filename(self, docId):
        filename = self.file_names[docId // 500]
        return filename

    def get_original_passage_content(self, docId):
        filename = self.file_names[docId // 500]
        with open(self.original_files_dir + filename) as f:
            passages = f.read().split("$$$")
            return passages[(docId % 500)]

    def get_next_document(self):
        if self.current_file_index >= len(self.file_names):
            return None
        with open(self.path + "/" + self.file_names[self.current_file_index]) as f:
            self.current_file_index += 1
            return f.read()


class Corpus:
    def __init__(self, reader):
        """Map<docId, Document>"""
        self.documents = {}
        self.average_document_length = 0
        self.build_corpus(reader)

    def update_average(self, added_len):
        self.average_document_length = (
            self.average_document_length * len(self.documents) + added_len
        ) / (len(self.documents) + 1)

    def build_corpus(self, reader):
        current_document = -1
        while True:
            current_document += 1
            document_content = reader.get_next_document()
            if document_content == None:
                break
            passages = document_content.split("$$$")
            passage_number = 0
            for passage in passages:
                terms = passage.split()
                self.update_average(len(terms))
                map_terms = {}
                for term in terms:
                    if term in map_terms:
                        map_terms[term] += 1
                    else:
                        map_terms[term] = 1
                docId = passage_number + 500 * current_document
                passage_number += 1
                # self.documents.append(Document(map_terms, docId))
                self.documents[docId] = Document(map_terms, docId)

    def get_document(self, docId):
        return self.documents[docId]


# Term in how many documents
class InvertedIndex:
    def __init__(self, corpus):
        # Map <term, docId>
        self.index = {}
        self.corpus = corpus
        self.build_index(corpus)

    def add_document_to_index(self, document):
        docid = document.docId
        for term in document.map_of_terms:
            if term in self.index:
                self.index[term].append(docid)
            else:
                self.index[term] = [docid]

    def build_index(self, corpus):
        for document in corpus.documents:
            self.add_document_to_index(corpus.documents[document])

    def get_posting_list(self, term):
        if term in self.index:
            return self.index[term]
        else:
            return []

    # AND
    # 1 2 3 4 5
    # 2 3 5 7
    # 2 3 5
    def get_documents_for_query_AND(self, query_terms):
        # query_terms = query.split(" ")
        term_pointer = 1  # current
        result = self.get_posting_list(query_terms[0])
        while term_pointer < len(query_terms):
            ir = 0
            ic = 0
            result_temp = []
            posting_list = self.get_posting_list(query_terms[term_pointer])
            while ir < len(result) and ic < len(posting_list):
                if result[ir] < posting_list[ic]:
                    ir += 1
                elif result[ir] > posting_list[ic]:
                    ic += 1
                else:
                    result_temp.append(result[ir])
                    ir += 1
                    ic += 1
            result = result_temp
            term_pointer += 1
        return result

    # 1 2 4 5
    # 2 3 5 7
    def get_documents_for_query_OR(self, query_terms):
        # query_terms = query.split(" ")
        term_pointer = 1  # current
        result = self.get_posting_list(query_terms[0])
        while term_pointer < len(query_terms):
            ir = 0
            ic = 0
            result_temp = []
            posting_list = self.get_posting_list(query_terms[term_pointer])
            while ir < len(result) and ic < len(posting_list):
                if result[ir] < posting_list[ic]:
                    result_temp.append(result[ir])
                    ir += 1
                elif result[ir] > posting_list[ic]:
                    result_temp.append(posting_list[ic])
                    ic += 1
                else:
                    result_temp.append(result[ir])
                    ir += 1
                    ic += 1
            while ir < len(result):
                result_temp.append(result[ir])
                ir += 1
            while ic < len(posting_list):
                result_temp.append(posting_list[ic])
                ic += 1
            result = result_temp
            term_pointer += 1
        return result

    def subtract(self, list1, list2):
        i = 0
        j = 0
        result = []
        while i < len(list1) and j < len(list2):
            if list1[i] < list2[j]:
                result.append(list1[i])
                i += 1
            elif list1[i] > list2[j]:
                j += 1
            else:
                i += 1
                j += 1
        while i < len(list1):
            result.append(list1[i])
            i += 1
        return result

    def idf(self, query_term):
        N = len(self.corpus.documents)
        nqi = len(self.get_posting_list(query_term))
        return math.log((N + 1) / (nqi + 0.5))

    def BM25(self, document, query, k1, b):
        score = 0
        terms = query.split(" ")
        for term in terms:
            if term in document.map_of_terms:
                score += (
                    self.idf(term)
                    * document.map_of_terms[term]
                    * (k1 + 1)
                    / (
                        document.map_of_terms[term]
                        + k1
                        * (
                            1
                            - b
                            + b
                            * document.numberOfTerms
                            / self.corpus.average_document_length
                        )
                    )
                )
            else:
                pass
                # print(
                #     "Not found term" + str(term) + "in document" + str(document.docId)
                # )
        return score


class Query:
    def __init__(self, query):
        self.was_corrected = False
        self.query = normalise_query(query)
        self.query = self.spell_check()
        self.query_terms = self.query.split(" ")

    def spell_check(self):
        return self.query
        b = TextBlob(self.query)
        corrected = b.correct()
        if corrected != self.query:
            self.was_corrected = True
            return str(corrected)
        else:
            return self.query

    def retrieve_documents(self, reader, corpus, inverted_index):
        docs = inverted_index.get_documents_for_query_OR(self.query_terms)
        docs_with_bm25 = {}
        for doc in docs:
            docs_with_bm25[doc] = inverted_index.BM25(
                corpus.get_document(doc), self.query, k1, b
            )
        # print(docs_with_bm25)
        sorted_docs = sorted(
            docs_with_bm25.items(), key=lambda item: item[1], reverse=True
        )
        sorted_docIds = [x[0] for x in sorted_docs]
        sorted_docs_with_filenames = map(
            lambda x: {
                "docId": x,
                "filename": reader.get_original_passage_filename(
                    corpus.get_document(x).docId
                ),
                "content": reader.get_original_passage_content(
                    corpus.get_document(x).docId
                ),
                "bm25": docs_with_bm25[x],
            },
            sorted_docIds,
        )
        return list(sorted_docs_with_filenames)


def init():
    reader = Reader(path="Normal", original_files_dir="Unnormal/")
    corpus = Corpus(reader)
    inverted_index = InvertedIndex(corpus)
    return reader, corpus, inverted_index


def search(reader, corpus, inverted_index, query):
    query = Query(query)
    docs = query.retrieve_documents(reader, corpus, inverted_index)
    return docs


def build_index_and_search(query):
    reader = Reader("Normal")
    corpus = Corpus(reader)
    inverted_index = InvertedIndex(corpus)
    # print(inverted_index.get_posting_list("contamin"))
    query = Query(query)
    docs = query.retrieve_documents(reader, corpus, inverted_index)
    return docs


def spell_check(query):
    b = TextBlob(query)
    corrected = b.correct()
    if corrected != query:
        return corrected
    else:
        return None


# main()