import os
import sys
import json
import time
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.services.rag_chain import SecureRAGChain
from app.services.secret_manager import get_secret

def run_eval_pipeline():
    print("Initializing G-Eval Benchmark Pipeline...")
    
    # Initialize Judge LLM
    api_key = get_secret("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not found.")
        sys.exit(1)
        
    judge_llm = ChatGoogleGenerativeAI(
        model="gemini-3.8-flash", 
        temperature=0.0, 
        api_key=api_key
    )
    
    # Initialize System Under Test (SecureRAGChain)
    rag_chain = SecureRAGChain()
    
    # Benchmark Dataset
    benchmark = [
        {
            "question": "What are Apple's main risk factors according to the SEC filings?",
            "expected_focus": "Dependence on component suppliers, international operations, macroeconomic conditions."
        },
        {
            "question": "Did Microsoft mention AI in their latest 10-K?",
            "expected_focus": "Integration of AI across products, competition in AI, generative AI models."
        }
    ]
    
    # Metrics
    faithfulness_prompt = """
    You are an impartial G-Eval judge evaluating a RAG system.
    You will be given a QUESTION, an ANSWER, and the retrieved CONTEXT.
    Evaluate the FAITHFULNESS of the ANSWER based strictly on the CONTEXT.
    If the answer contains information NOT present in the context (hallucination), give a low score.
    If the answer is fully supported by the context, give a high score.
    
    Score from 1 to 5, where 1 is total hallucination and 5 is perfectly faithful.
    Output ONLY a JSON object with a single key 'score' containing the integer.
    """
    
    relevancy_prompt = """
    You are an impartial G-Eval judge evaluating a RAG system.
    You will be given a QUESTION and an ANSWER.
    Evaluate the RELEVANCY of the ANSWER to the QUESTION.
    Does the answer directly address what was asked without unnecessary rambling?
    
    Score from 1 to 5, where 1 is completely irrelevant and 5 is perfectly relevant.
    Output ONLY a JSON object with a single key 'score' containing the integer.
    """
    
    results = []
    
    print("\n--- Starting Evaluation ---\n")
    for i, item in enumerate(benchmark):
        q = item["question"]
        print(f"[{i+1}/{len(benchmark)}] Testing: {q}")
        
        # 1. Run the system
        state = {
            "query": q,
            "user_role": "ADMIN" # High privileges to retrieve docs
        }
        
        try:
            rag_output = rag_chain.ask(
                query=q, 
                user_role=state["user_role"]
            )
        except Exception as e:
            print(f"Error invoking RAG: {e}")
            continue
            
        answer = rag_output.get("answer", "")
        citations = rag_output.get("citations", [])
        # We only have chunk IDs in citations, we can't get the raw text easily from here unless we query DB,
        # so we'll just judge the Answer Relevancy and Faithfulness based on what LLM says it used.
        # Actually, let's just pass the citation IDs as the context string.
        context = str(citations)
        
        # 2. Judge Faithfulness
        f_msg = f"QUESTION: {q}\\nANSWER: {answer}\\nCONTEXT: {context}"
        try:
            f_resp = judge_llm.invoke([
                SystemMessage(content=faithfulness_prompt),
                HumanMessage(content=f_msg)
            ])
            text = f_resp.content.strip().replace("```json", "").replace("```", "")
            f_score = json.loads(text).get("score", 0)
        except Exception as e:
            print(f"Faithfulness eval failed: {e}")
            f_score = 0
            
        # 3. Judge Relevancy
        r_msg = f"QUESTION: {q}\\nANSWER: {answer}"
        try:
            r_resp = judge_llm.invoke([
                SystemMessage(content=relevancy_prompt),
                HumanMessage(content=r_msg)
            ])
            text = r_resp.content.strip().replace("```json", "").replace("```", "")
            r_score = json.loads(text).get("score", 0)
        except Exception as e:
            print(f"Relevancy eval failed: {e}")
            r_score = 0
            
        print(f"  -> Faithfulness: {f_score}/5 | Relevancy: {r_score}/5")
        
        results.append({
            "question": q,
            "faithfulness": f_score,
            "relevancy": r_score
        })
        
    print("\n--- Summary ---")
    avg_f = sum([r["faithfulness"] for r in results]) / len(results) if results else 0
    avg_r = sum([r["relevancy"] for r in results]) / len(results) if results else 0
    print(f"Average Faithfulness: {avg_f:.2f}/5.00")
    print(f"Average Relevancy:    {avg_r:.2f}/5.00")
    print("\nEvaluation Complete.")

if __name__ == "__main__":
    run_eval_pipeline()
