import sys
from agents.zuora_agent import agent
from rich.console import Console
from rich.panel import Panel

console = Console()

def main():
    console.print(Panel.fit("[bold blue]Zuora Seed Agent[/bold blue]\n[italic]Powered by Strands SDK[/italic]", border_style="blue"))
    console.print("Hello! I'm Zuora Seed. I can help you manage your Product Catalog or answer Billing Architecture questions.")
    console.print("Try: 'Help me create a new product' or 'How do I handle prepaid billing?'\n")

    while True:
        try:
            user_input = console.input("[bold green]You > [/bold green]")
            if user_input.lower() in ["exit", "quit"]:
                console.print("[blue]Goodbye![/blue]")
                break
            
            if not user_input.strip():
                continue

            # Strands agent execution
            # The SDK documentation says: agent(prompt) returns the response
            # We catch exceptions in case of configuration errors (missing keys)
            try:
                response = agent(user_input)
                # The response might be a string or an object depending on the SDK version.
                # Assuming string or object with __str__
                console.print(f"\n[bold cyan]Zuora Seed:[/bold cyan] {response}\n")
            except Exception as e:
                console.print(f"\n[bold red]Error running agent:[/bold red] {e}")
                console.print("[italic]Note: Ensure you have AWS credentials configured for Bedrock or the appropriate model provider.[/italic]\n")
        
        except KeyboardInterrupt:
            console.print("\n[blue]Goodbye![/blue]")
            break

if __name__ == "__main__":
    main()
