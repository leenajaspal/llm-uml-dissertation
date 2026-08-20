# Prompt 1: Prose

You are building a backend application. Read the following for the full requirements and produce a complete, working implementation. Produce the complete application as downloadable Python files, one per module, including a dependency file. Do not ask clarifying questions; make reasonable decisions and proceed.

Build the application in Python using the FastAPI framework, with SQLite for storage. Use only widely available libraries. Do not use any external payment service.

The application must expose exactly the following endpoints, using these paths, these request field names, and these response field names. All request and response bodies are JSON. All monetary values are integers representing pence.

Endpoints (all request/response bodies are JSON; all amounts are integer pence):

POST /auth/register   — request: email, password   — response: user_id, email   — 201\
POST /auth/login      — request: email, password   — response: access_token    — 200\
GET  /accounts/me     — response: account_id, balance_pence, currency          — 200\
POST /deposits        — request: amount_pence       — response: transaction_id, status, balance_pence — 201\
POST /withdrawals     — request: amount_pence       — response: transaction_id, status, balance_pence — 201\
POST /transfers       — request: recipient_email, amount_pence — response: transaction_id, status, balance_pence — 201\
GET  /transactions    — response: list of { transaction_id, type, amount_pence, direction, status, created_at } — 200\
POST /transactions/{transaction_id}/reversal — response: transaction_id, reverses_transaction_id, status — 201

Authenticated endpoints expect the credential returned by /auth/login in an Authorization header as a bearer token.

The table above covers successful requests only. How the application responds to invalid, unauthorised or rejected requests is for you to decide.

Requirements:

I want to build a simple payments app. The idea is that people can keep a balance in the app and send money to each other, like the wallet features you get in banking apps now. This is a first version to get something working, so it only needs to do the basics.

People sign up with their email address and a password and then log in whenever they want to use it. Once they are logged in they should be able to see how much money they currently have.

Users need to be able to put money into their account and take money back out again. I am not dealing with real card payments or bank transfers at this stage, so for now the app can assume that side of it has already been handled and simply add or remove the money. 

The main feature of this app is sending money to other people. A user can pick the person they want to pay by their email address, put in an amount, and the money moves across. The app shouldn’t allow anyone to send money they don’t actually have.

There should also be a daily cap of £1000 so that nobody can move very large amounts in one go. This is to limit the damage if someone’s account gets taken over.

People should be able to look back over what they have sent and received, so there needs to be some sort of history they can view. They should only ever be able to see their own transactions and not anybody else’s.

Sometimes a payment will be made by mistake, so there needs to be a way of reversing one that has already gone through and putting the money back where it came from. 

The most important thing overall is that the money always adds up properly. There cannot be a situation where money disappears, or gets counted twice, or where somebody’s balance doesn’t match what has actually happened on their account. This is people’s money, so it also needs to be secure and their details need to be properly protected.



