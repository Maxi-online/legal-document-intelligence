# Guide to the use of wet data

## Brief description

DocumentIntelligence automatically uses the data for testing if the Casebook API key is not specified in `settings.json`. This allows the entire system to be run and tested without connection to the real API.

## Fast start

### 1. Moose mode settings

In the `settings.json` file ** Don't specify** actual Casebook API key:

```json
{
  "openai": {
    "api_key": "yours_openai_key"
  },
  "casebook": {
    "api_key": "your_casebook_api_key_here",
    "base_url": "https://api.casebook.ru"
  }
}
```

Or leave it empty:

```json
{
  "casebook": {
    "api_key": "",
    "base_url": "https://api.casebook.ru"
  }
}
```

### 2. Start the system

```bash
# Launching through Docer Compase
docker-compose up -d

# Or launch without Docker (as usual)
# The system will automatically determine the absence of the key and use moss data
```

### 3. Testing

1. Open the front: http://localhost:3000
2. Enter any request (e.g. "Ivans Demo Individual"")
3. Select a search type (FIO, INN, or name)
4. Press "Find"
5. The system automatically uses the moss data and will process it through the GPT agents

## How does it work?

1. The service checks the availability of the API key in `settings.json`
2. If the key is missing or equals the default value, the wet data shall be used
3. If the key is specified, the real casebook API request is executed
4. In case of error connection to the real API - automatic fallback on the mock data

## Test data

The data includes 5 fixed scenarios + a large set so that the demonstration is visible even with a large number of acts.

| Scenario ♪ Case number ♪ Type of reference ♪ Description |
|----------|------------|----------------|----------|
| Claimant A40-12345/2024 ♪ claimant ♪ claimer ♪ |
| Respondent A41-67890/2024 ♪ Respondent ♪ The person against whom the claim is brought |
| A50-11111/2023 ♪ Third party Original Air Date on October 14, 2013 |
| Counterparty A43-2222/2024 ♪ counterparty ♪ Party to the contract |
| Reference to A55-33333/2023 ♪ reference ♪ simple reference in text |

### Scale

By default, the wet generator returns **tens/head** results with:

- different vessels/regions/dates/types of acts
- multiple references (mentions_count),
- writing/rotation/rotation/pull typing,
- `act_url` control duplicates to verify deduplication.

You can control the size through the variable environment:

```bash
MOCK_RESULTS_COUNT=120
```

Each result contains a complete set of data:
- Case number and court
- Date of act
- Reference to act
- List of parties
- Full text of the judicial act
- Context of reference
- Type of reference
- Metadata (region, category, number of references)

## Testing of processing agents

The wet data are fully compatible with the GPT agents:

### Context Extraction Agent
- Extract the context from the full text of the act
- Works with all kinds of references.

### Classification Agent  
- Classify the role (claimer/defendant/participant, etc.)
- Uses the type of reference and the text of the act

### Relevance Ranking Agent
- Assesss relevance by number of references
- Taking into account the role in the process
- Early results

## Example of full cycle

```bash
# 1. Run the system
docker-compose up -d

# 2. Open the front
# http://localhost:3000

# 3. Do a search
# Request: "Ivans Demo Individual"
# Type: FIO

# 4. System automatically:
# - Using wet data (5 results)
# - Processing through GPT agents.
# - Saves it at PostgreSQL.
# - Cashing in Redis.
# - Shows the results on the front line.

# 5. Check the results:
# - A table of the files found.
# - Court filters, type of reference
# - Export to Excel/PDF/JSON
```

## Switch to Real API

When the real API key is ready:

1. Please specify in `settings.json`:
```json
{
  "casebook": {
    "api_key": "yours_Real_key_from_casebook",
    "base_url": "https://api.casebook.ru"
  }
}
```

2. Restart service:
```bash
docker-compose restart pravo_api_service
```

The system will automatically switch to a real API.

## Benefits

✅ **Automatic switching** - No need to change code or configuration  
✅ **Full functionality** - all modules work as real data  
✅ **Quick testing** - no delay in real requests  
✅ **Scenario diversity** - different types of references for testing  
✅ **Free** - no real API limits spent  

## Mocular data structure

The `mock_data.py` file contains:

- `generate_mock_casebook_response() & = random data generation
- `get_extended_mock_data() ` - fixed test scenarios

All data in a format that is fully compatible with the actual API Casebook.

## Debugging

If it is necessary to check if the moose data are used:

```bash
# Look at the service logs.
docker-compose logs pravo_api_service

# You'll see either:
# - Messages on the use of moc data (if key not specified))
# - Real API requests (if specified)
```
