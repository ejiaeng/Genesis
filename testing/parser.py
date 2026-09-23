import re
import json
import argparse

def parse_questions(text):
    """
    Parses a block of text containing multiple choice questions and returns a list of dictionaries.
    """
    questions = []
    
    # Split the text by question number (e.g. "1. ", "2. ")
    blocks = re.split(r'\n(?=\d+\.\s+)', text.strip())
    
    for block in blocks:
        if not block.strip():
            continue
            
        # Extract question number and text
        q_match = re.match(r'(\d+)\.\s+(.*?)(?=\nA\.)', block, re.DOTALL)
        if not q_match:
            continue
            
        q_num = int(q_match.group(1))
        q_text = q_match.group(2).strip().replace('\n', ' ')
        
        # Extract options (A, B, C, D)
        options = {}
        opt_pattern = r'([A-D])\.\s+(.*?)(?=\n[A-D]\.|\n[A-D]:)'
        for opt_match in re.finditer(opt_pattern, block, re.DOTALL):
            opt_letter = opt_match.group(1)
            opt_text = opt_match.group(2).strip().replace('\n', ' ')
            options[opt_letter] = opt_text
            
        # Extract answer (e.g., from B:B:Gn:1, correct answer is the first letter 'B')
        ans_match = re.search(r'\n([A-D]):.*', block)
        correct_answer = ans_match.group(1) if ans_match else None
        
        questions.append({
            "id": q_num,
            "question": q_text,
            "options": options,
            "correct_answer": correct_answer
        })
        
    return questions

def main():
    parser = argparse.ArgumentParser(description="Parse Genesis Multiple Choice Questions PDF text.")
    parser.add_argument("input_file", help="Path to the input text file containing the raw OCR output")
    parser.add_argument("output_file", help="Path to the output JSON file")
    
    args = parser.parse_args()
    
    with open(args.input_file, 'r', encoding='utf-8') as f:
        text = f.read()
        
    questions = parse_questions(text)
    
    with open(args.output_file, 'w', encoding='utf-8') as f:
        json.dump(questions, f, indent=4)
        
    print(f"Successfully parsed {len(questions)} questions into {args.output_file}")

if __name__ == "__main__":
    main()
