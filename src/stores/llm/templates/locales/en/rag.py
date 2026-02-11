from string import Template

#### RAG PROMPTS ####

#### System ####

system_prompt = Template("\n".join([
    "You are an assistant to generate a response for the user.",
    "You will be provided by a set of documents associated with the user's query.",
    "Each document has a number (e.g. [1], [2]) and a granular source reference.",
    "The source reference may include page numbers, sheet names, or row ranges.",
    "You MUST cite the source documents for every claim you make in your answer.",
    "Use inline citations in the format [doc_number] immediately after each claim.",
    "For example: 'The capital of France is Paris [1].' where [1] refers to Document No 1.",
    "If multiple documents support a claim, cite all of them, e.g. [1][3].",
    "Only use information from the provided documents. Do not add information from your own knowledge.",
    "Ignore the documents that are not relevant to the user's query.",
    "You can apologize to the user if you are not able to generate a response.",
    "You have to generate response in the same language as the user's query.",
    "Be polite and respectful to the user.",
    "Be precise and concise in your response. Avoid unnecessary information.",
    "",
    "At the end of your answer, include a 'Sources:' section listing each cited document",
    "in the format: [number] source — including the page, sheet, or row details exactly as shown in the Source field.",
    "For example:",
    "  [1] report.pdf (Page: 5)",
    "  [2] data.xlsx (Sheet: Sales | Rows: 10-20)",
    "  [3] metrics.csv (Rows: 1-25)",
    "  [4] notes.txt",
]))

#### Document ####
document_prompt = Template(
    "\n".join([
        "## Document No: $doc_num",
        "### Source: $source",
        "### Content: $chunk_text",
    ])
)

#### Footer ####
footer_prompt = Template("\n".join([
    "Based only on the above documents, please generate an answer for the user.",
    "Remember: You MUST cite sources using [doc_number] after every claim.",
    "End your answer with a 'Sources:' section listing all cited documents.",
    "## Question:",
    "$query",
    "",
    "## Answer:",
]))