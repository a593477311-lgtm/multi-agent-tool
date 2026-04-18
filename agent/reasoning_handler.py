from typing import Optional

class ReasoningHandler:
    def __init__(self, show_reasoning: bool = True):
        self.show_reasoning = show_reasoning
        self.buffer = ""
        self._in_reasoning_block = False
    
    def handle_chunk(self, reasoning_chunk: str) -> None:
        if not reasoning_chunk:
            return
        
        self.buffer += reasoning_chunk
        
        if self.show_reasoning:
            if not self._in_reasoning_block:
                print("\n\033[90m🤔 思考中...\n\033[90m", end="", flush=True)
                self._in_reasoning_block = True
            
            print(f"\033[90m{reasoning_chunk}\033[0m", end="", flush=True)
    
    def get_full_reasoning(self) -> str:
        return self.buffer
    
    def reset(self) -> None:
        self.buffer = ""
        self._in_reasoning_block = False
    
    def end_reasoning_block(self) -> None:
        if self._in_reasoning_block:
            print("\033[0m\n", end="", flush=True)
            self._in_reasoning_block = False
