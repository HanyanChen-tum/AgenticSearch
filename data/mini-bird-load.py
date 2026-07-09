from datasets import load_dataset

dataset = load_dataset("birdsql/bird_mini_dev")

print(dataset["mini_dev_sqlite"][0])