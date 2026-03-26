# Inference Input Schema

## Feature Order (for `instances` array format)

| Position | Feature | Type | Description |
|----------|---------|------|-------------|
| 0 | distance_from_home | float | Distance from cardholder's home |
| 1 | distance_from_last_transaction | float | Distance from last transaction |
| 2 | ratio_to_median_purchase_price | float | Ratio to median purchase price |
| 3 | repeat_retailer | float (0/1) | Whether transaction was at a repeat retailer |
| 4 | used_chip | float (0/1) | Whether chip was used |
| 5 | used_pin_number | float (0/1) | Whether PIN was used |
| 6 | online_order | float (0/1) | Whether it was an online order |

## Example Request

curl -X POST http://fraud-detector.mlops-workshop.svc.cluster.local/v1/models/fraud-detector:predict \
  -H "Content-Type: application/json" \
  -d '{"instances": [[75.74, 0.53, 1.18, 1.0, 0.0, 0.0, 1.0]]}'

## Expected Response

{"predictions": [0]}  (0 = not fraud, 1 = fraud)
