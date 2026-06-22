AgenticSearch is a research project focused on Text-to-SQL generation using LLMs and agentic reasoning over the Spider dataset.

We compare three approaches:

Baseline 1: Direct LLM → SQL from schema
Baseline 2: LLM with schema + table/column selection
Baseline 3 (Agent): Multi-step agent with database exploration + tool use

Current Experimental Results (Qwen 3B, Spider Sample)
100-sample evaluation
Method	Accuracy	Notes
Baseline 1	0.52	Direct schema prompting
Baseline 2	0.63	Best-performing baseline
Baseline 3 Agent	0.58	Tool-based reasoning (multi-step)

Baseline 1 — Direct Schema Prompting
Input: question + full schema
Output: SQL
No retrieval or table selection
Baseline 2 — Schema + Filtering
Selects top-k tables/columns
Smaller context → better accuracy
Baseline 3 — Agentic DB Reasoning
Iterative reasoning loop
Tool calls:
schema inspection
sample rows
SQL generation
Uses max_steps loop
Outputs traceable reasoning

We are not optimizing for "agent complexity".

We are optimizing for:

highest SQL execution accuracy per cost 


"Standard LLMs treat massive data like a reading comprehension test. If you feed an LLM 100,000 tokens, its neural attention gets stretched thin. It gets distracted, forgets instructions, and starts hallucinating. RLM solves this by treating the LLM not as a reader, but as a Software Engineer. Instead of reading the data, the RLM writes Python code to query the data inside a secure sandbox."

The State Observation: The agent reads the system prompt (which contains the tools it is allowed to use) and the current terminal output.

The Reasoning Phase (Internal): The model's neural network predicts the best programmatic way to solve the problem based on standard coding logic.

The Action (Coding): The agent writes raw Python code to execute its plan.

The Interception: The RLM Python framework intercepts the code, stops the AI from talking, and drops the code into the Sandbox.

The Execution: The computer's CPU runs the code and captures any prints or errors.

The Return: The RLM framework feeds the CPU's terminal output back to Step 1.

The Exit (FINAL): If the terminal output answers the user's question, the agent calls FINAL().


"Before we dive into the SQL implementation for the BIRD benchmark, I wanted to rigorously validate the underlying architecture. Over the last week, I built a local sandbox using a 7B parameter model to test the core claims of the MIT Recursive Language Model (RLM) framework. My goal was to prove that this architecture actually cures the three biggest weaknesses of standard LLMs: logic failure, context rot, and multi-step hallucination."

Part 2: The Sandbox Proofs (What You Achieved)

Walk them through your three experiments. Focus on the results and what they mean, not just the code.

    What to say:
    "I ran three isolated stress tests, and the results were completely successful:

        Bypassing Logic Limits: I gave the model a massive text and asked it to do complex counting and math. A standard LLM hallucinates the math. My RLM agent wrote a Python script to do it. This proved that we can offload deterministic math directly to the CPU, guaranteeing 100% accuracy.

        Curing Context Rot: I fed the model 600,000 characters of junk server logs to find one hidden password. The standard model suffered total attention dilution and failed. The RLM agent kept the data locked in RAM and wrote a Regex script to extract it instantly. This proved the AI never actually has to 'read' massive datasets to analyze them.

        Solving Complex Delegation (Recursion): I built a multi-table scenario where finding a password required looking up an ID first. The 'Parent' agent successfully paused its own execution, spawned a clean 'Child' agent to fetch the ID, and then used that ID to finish the job. This proved that programmatic delegation prevents the AI from getting confused by complex relationships."

Part 3: The Translation (The "Aha!" Moment)

This is where you connect your text experiments to your Master's thesis (SQL).

    What to say:
    "What these experiments proved to me is that the RLM architecture is completely data-agnostic. The AI doesn't need to read the data; it just needs a safe set of tools to explore it.

    The exact same generalized 'Reason + Act' loop I just validated for text maps perfectly to our SQL database problem.

        Instead of searching a text variable, the sandbox will hold a live SQLite connection.

        Instead of text-parsing tools, I will give the agent SQL tools like db.get_tables() and db.execute().

        Instead of the Child agent reading a text block, the Parent will spawn a Child to write sub-queries for specific tables."

Part 4: The Action Plan (Next Steps)

End the presentation by telling them exactly what you are doing next week. It shows you don't need them to assign you homework.

    What to say:
    "Now that the core engine is validated, I am shifting entirely to the DB-RLM implementation. My immediate next steps are:

        Building the Database Bridge: I am writing a secure Python class (db_context.py) that connects the RLM sandbox to SQLite.

        Designing the Master Prompt: I am drafting a dynamic System Prompt that forces the Parent Agent into a strict workflow: it must use get_schema() to verify columns before it is ever allowed to write a SELECT statement. This will physically prevent SQL hallucination.

        Initial BIRD Testing: Once the bridge is built, I will pipe the first few complex questions from the BIRD benchmark directly into the system to test the dynamic exploration."

If They Ask About the Codebase...

If your supervisor asks to see your code or notices the long list of files in the MIT repo:

    Point to core.py and repl.py: "I spent a lot of time analyzing the engine room. core.py handles the ReAct loop, and repl.py handles the secure sandbox. I actually had to patch core.py to sanitize markdown formatting so it would work seamlessly with our local models."

    Point to your custom files: "I bypassed the generic MIT demos and built my own custom test suite (like recursion_test.py) because I needed to verify the exact mechanics we will use for SQL."

baselines : 
python scripts/run_baseline_1.py \ --dataset data/processed/dev_questions_sample_100.json \ --output results/baseline_1_qwen3b_sample100_aziz.json

RLM: 
python examples/recursion_test.py