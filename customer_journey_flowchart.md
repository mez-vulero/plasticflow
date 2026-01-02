flowchart LR
  Lead["Customer Lead or Inquiry"] --> Quote["Price and Availability Check"]
  Quote --> SO["Sales Order Cash or Credit"]

  SO --> PayPending["Payment Pending"]
  SO --> CreditSO["Credit Sales Approved"]

  PayPending --> PaySlip["Payment Slips Uploaded and Verified"]
  PaySlip --> PayVerified["Payment Verified"]
  PayVerified --> Invoice["Invoice"]
  CreditSO --> Invoice

  Invoice --> GatePass["Gate Pass Generated"]
  GatePass --> Delivery["Delivery Note"]
  Delivery --> Completion["Order Completed"]

  SO --> ImportNeed{"Import Needed"}
  ImportNeed --> PO["Purchase Order"]
  ImportNeed --> Invoice

  PO --> Shipment["Import Shipment and Items"]
  Shipment --> LandCost["Landing Cost Worksheet"]
  LandCost --> Stock["Stock Entries and Landed Cost Allocation"]

  Stock --> Ready["Ready for Delivery"]
  Ready --> GatePass
  Invoice --> Collections["Collections Timeline and Outstanding Tracking"]

  subgraph Reporting_and_Control["Reporting and Control"]
    DailySales["Daily Sales Chart"]
    StatusBreak["Sales Order Status Breakdown"]
    Mix["Sales Mix"]
    Pipeline["Pipeline Cycle Time"]
    StockVal["Stock Value and Ageing"]
    Profit["Profitability Summary"]
  end

  SO --> DailySales
  SO --> StatusBreak
  SO --> Mix
  SO --> Pipeline
  Stock --> StockVal
  SO --> Profit
