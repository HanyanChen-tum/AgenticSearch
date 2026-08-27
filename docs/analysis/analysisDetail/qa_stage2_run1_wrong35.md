### bird_1068   [被拦过]
题面: From 2010 to 2015, what was the average overall rating of players who are higher than 170?
hint: 
--- 模型的分析 ---
  answer_shape: "One column: the average overall rating"
  counting_unit: "Table rows, because the average is defined over matching records rather than distinct people"
  stated_conditions: ["use dates from 2010 through 2015 inclusive", "include only players whose height is greater than 170"]
  unit_and_scale: "Average overall rating, not a percentage; no x100 conversion"
  ambiguities: ["whether the average should be over all matching rating records or one record per player, though the provided hint defines it as row-based"]
--- 被拦的 SQL ---
  SELECT SUM(t2.overall_rating) * 1.0 / COUNT(t2.id) FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_api_id = t2.player_api_id WHERE strftime('%Y', t2.date) >= '2010' AND strftime('%Y', t2.date) <= '2015' AND t1.height > 170
--- 最终 SQL ---
  SELECT SUM(t2.overall_rating) * 1.0 / COUNT(t2.id) FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_api_id = t2.player_api_id WHERE strftime('%Y', t2.date) >= '2010' AND strftime('%Y', t2.date) <= '2015' AND t1.height > 170
--- gold SQL ---
  SELECT AVG(t2.overall_rating) AS avg_rating
FROM `Player` AS t1
JOIN `Player_Attributes` AS t2 ON t1.player_api_id = t2.player_api_id
WHERE t1.height > 170
  AND strftime('%Y', t2.`date`) BETWEEN '2010' AND '2015';
模型答: [[68.85402657670379]]
gold答: [[68.90135724487692]]

### bird_1149   [未拦]
题面: Among male patients, what is the ratio of in-patients to outpatients?
hint: 
--- 模型的分析 ---
  answer_shape: "Return one column containing the numeric ratio of male in-patients to male outpatients."
  counting_unit: "Patients / records matching the stated conditions."
  stated_conditions: ["Consider only male patients", "Male means SEX = 'M'", "In-patient means Admission = '+'", "Outpatient means Admission = '-'", "Compute ratio as count of male in-patients divided by count of male outpatients"]
  unit_and_scale: "A unitless ratio; no percentage conversion or x100 scaling is required."
  ambiguities: ["It is not stated how to handle a zero outpatient count, though the hint defines the ratio directly."]
--- 最终 SQL ---
  SELECT 1.0 * (SELECT COUNT(ID) FROM Patient WHERE SEX = 'M' AND Admission = '+') / (SELECT COUNT(ID) FROM Patient WHERE SEX = 'M' AND Admission = '-')
--- gold SQL ---
  SELECT CAST(SUM(CASE WHEN Admission = '+' THEN 1 ELSE 0 END) AS REAL) * 100 / SUM(CASE WHEN Admission = '-' THEN 1 ELSE 0 END) FROM Patient WHERE SEX = 'M'
模型答: [[0.8317757009345794]]
gold答: [[83.17757009345794]]

### bird_1169   [未拦]
题面: What is the ratio of male to female patients among all those with abnormal uric acid counts?
hint: 
--- 模型的分析 ---
  answer_shape: "1 column: the male-to-female ratio of patients with abnormal uric acid results"
  counting_unit: "patients, not raw rows, because the question asks about patients among those with abnormal uric acid counts"
  stated_conditions: ["male refers to SEX = 'M'", "female refers to SEX = 'F'", "abnormal uric acid refers to UA <= 8.0 for males", "abnormal uric acid refers to UA <= 6.5 for females"]
  unit_and_scale: "a unitless ratio; no percentage conversion"
  ambiguities: ["Whether to count distinct patients or laboratory records if a patient has multiple abnormal uric acid results", "Whether the requested ratio should be male divided by female or expressed in some other ordering"]
--- 最终 SQL ---
  SELECT 1.0 * SUM(CASE WHEN P.SEX = 'M' AND L.UA <= 8.0 THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN P.SEX = 'F' AND L.UA <= 6.5 THEN 1 ELSE 0 END), 0) AS Ratio FROM Laboratory AS L INNER JOIN Patient AS P ON L.ID = P.ID;
--- gold SQL ---
  SELECT CAST(COUNT(DISTINCT CASE WHEN T2.UA <= 8.0 AND T1.SEX = 'M' THEN T1.ID ELSE NULL END) AS REAL) / COUNT(DISTINCT CASE WHEN T2.UA <= 6.5 AND T1.SEX = 'F' THEN T1.ID ELSE NULL END) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID
模型答: [[0.20566810835419985]]
gold答: [[0.184]]

### bird_125   [未拦]
题面: For loans contracts which are still running where client are in debt, state their district percentage unemployment rate increment from year 1995 to 1996.
hint: 
--- 模型的分析 ---
  answer_shape: "One numeric column giving the unemployment-rate increment percentage from 1995 to 1996."
  counting_unit: "Not counting entities; this is a rate calculation derived from matching loan contracts and district data."
  stated_conditions: ["Only loan contracts that are still running and where the client is in debt", "Loan status is D", "Use district unemployment rate for 1995 from A12", "Use district unemployment rate for 1996 from A13", "Compute increment as [(199
  unit_and_scale: "Percentage; multiply by 100 is required."
  ambiguities: ["Whether the result should be returned once per matching district or as a single overall value", "Whether district names should be included in the output or only the increment percentage"]
--- 最终 SQL ---
  SELECT 100.0 * (d.A13 - d.A12) / d.A12 FROM loan AS l INNER JOIN account AS a ON l.account_id = a.account_id INNER JOIN district AS d ON a.district_id = d.district_id WHERE l.status = 'D' AND d.A12 IS NOT NULL GROUP BY d.district_id ORDER BY d.district_id
--- gold SQL ---
  SELECT (d.A13 - d.A12) / d.A12 * 100 FROM loan AS l JOIN account AS a ON l.account_id = a.account_id JOIN district AS d ON a.district_id = d.district_id WHERE l.status = 'D' AND NOT d.A12 IS NULL AND NOT d.A13 IS NULL AND d.A12 > 0
模型答: [[115.0], [16.315789473684216], [9.782608695652177], [38.620689655172406], [20.0], [22.14285714285715], [28.387096774193544], [40.0], [13.636363636363
gold答: [[40.0], [39.259259259259245], [114.99999999999999], [22.499999999999993], [20.0], [11.666666666666679], [44.375], [13.333333333333346], [17.424242424

### bird_1339   [未拦]
题面: Calculate Elijah Allen’s average spend per event for events in September and October
hint: 
--- 模型的分析 ---
  answer_shape: "1 column: the average spend amount"
  counting_unit: "event-level spending rather than raw rows; if multiple expense records belong to the same event, they should be treated as that event’s spending"
  stated_conditions: ["the person is Elijah Allen", "use the full name as first_name plus last_name", "only include records where the month of the expense date is September or October", "calculate the average spend per event"]
  unit_and_scale: "currency amount; no percentage scaling"
  ambiguities: ["whether 'average spend per event' means averaging individual expense rows or averaging total spend aggregated to each event first", "whether the average should be computed over only events that have matching expenses in Septembe
--- 最终 SQL ---
  SELECT AVG(total_spend) FROM (SELECT ev.event_id, SUM(ex.cost) AS total_spend FROM expense ex JOIN member m ON ex.link_to_member = m.member_id JOIN budget b ON ex.link_to_budget = b.budget_id JOIN event ev ON b.link_to_event = ev.event_id WHERE m.first_name = 'Elijah' AND m.last_
--- gold SQL ---
  SELECT SUM(T2.cost)  / COUNT(DISTINCT link_to_budget)
FROM member AS T1 INNER JOIN expense AS T2 ON T1.member_id = T2.link_to_member 
WHERE T1.last_name = 'Allen' AND T1.first_name = 'Elijah' 
AND (SUBSTR(T2.expense_date, 6, 2) = '09' OR SUBSTR(T2.expense_date, 6, 2) = '10')
模型答: [[98.77]]
gold答: [[84.66]]

### bird_1472   [未拦]
题面: In 2012, who had the least consumption in LAM?
hint: 
--- 模型的分析 ---
  answer_shape: (无)
  counting_unit: (无)
  stated_conditions: (无)
  unit_and_scale: (无)
  ambiguities: (无)
--- 最终 SQL ---
  SELECT y.CustomerID FROM yearmonth AS y JOIN customers AS c ON y.CustomerID = c.CustomerID WHERE c.Segment = 'LAM' AND y.Date BETWEEN '201201' AND '201212' ORDER BY y.Consumption ASC LIMIT 1
--- gold SQL ---
  SELECT T1.CustomerID FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Segment = 'LAM' AND SUBSTR(T2.Date, 1, 4) = '2012' GROUP BY T1.CustomerID ORDER BY SUM(T2.Consumption) ASC LIMIT 1
模型答: [[7653]]
gold答: [[47273]]

### bird_1479   [未拦]
题面: Which year recorded the most consumption of gas paid in CZK?
hint: 
--- 模型的分析 ---
  answer_shape: "One column: the year that had the greatest total gas consumption for CZK-paid customers."
  counting_unit: "Not counting entities or rows; the question asks for the year with the largest aggregate consumption."
  stated_conditions: ["consider gas consumption", "consider payments made in CZK", "group or compare by year using the first 4 characters of Date"]
  unit_and_scale: "The answer is a year label, not a percentage or count."
  ambiguities: ["It is not explicit whether consumption should be summed across all matching records, but the wording 'most consumption' implies total consumption by year.", "It is not explicit whether negative consumption values should be handl
--- 最终 SQL ---
  SELECT CAST(substr(y.Date,1,4) AS INTEGER) AS year FROM yearmonth AS y INNER JOIN customers AS c ON y.CustomerID = c.CustomerID WHERE c.Currency = 'CZK' GROUP BY CAST(substr(y.Date,1,4) AS INTEGER) ORDER BY SUM(y.Consumption) DESC LIMIT 1
--- gold SQL ---
  SELECT SUBSTR(T2.Date, 1, 4) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Currency = 'CZK' GROUP BY SUBSTR(T2.Date, 1, 4) ORDER BY SUM(T2.Consumption) DESC LIMIT 1
模型答: [[2013]]
gold答: [["2013"]]

### bird_1482   [未拦]
题面: Provide the percentage increase in consumption paid in EUR between 2012 and 2013 for SME, LAM, and KAM respectively.
hint: 
--- 模型的分析 ---
  answer_shape: "Three percentage values, one each for SME, LAM, and KAM, in that order."
  counting_unit: "Entities are customers within each segment; the question asks for consumption totals by segment, not raw row counts."
  stated_conditions: ["Compare 2012 with 2013", "Use consumption paid in EUR only", "Return results for SME, LAM, and KAM", "Increase = 2013 consumption - 2012 consumption", "Percentage of Increase = (Increase / 2012 consumption) * 100%", "The year is
  unit_and_scale: "Percentage; multiply by 100 to express as percent."
  ambiguities: ["Whether the answer should be aggregated over all customers in each segment or calculated per customer and then summarized; the wording suggests segment-level totals.", "Whether the output should label the three values by segment
--- 最终 SQL ---
  WITH agg AS (SELECT c.Segment AS Segment, SUM(CASE WHEN substr(y.Date,1,4)='2012' THEN y.Consumption ELSE 0 END) AS cons2012, SUM(CASE WHEN substr(y.Date,1,4)='2013' THEN y.Consumption ELSE 0 END) AS cons2013 FROM yearmonth y JOIN customers c ON y.CustomerID = c.CustomerID WHERE 
--- gold SQL ---
  SELECT CAST((SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2013%', T2.Consumption, 0)) - SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2012%', T2.Consumption, 0))) AS FLOAT) * 100 / SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2012%', T2.Consumption, 0)), CAST(SUM(IIF(T1.Segment = 
模型答: [[734.7140627123255], [539.8291924960649], [553.2053767491262]]
gold答: [[734.7140627123255, 539.8291924960649, 553.2053767491262]]

### bird_1486   [未拦]
题面: How much more SMEs pay in Czech koruna than in euros? 
hint: 
--- 模型的分析 ---
  answer_shape: "one numeric column giving the difference in total spending between the two specified currency groups"
  counting_unit: "table rows representing transactions are summed, not distinct entities"
  stated_conditions: ["consider only SMEs", "use total pay made in Czech koruna", "use total pay made in euros", "compute how much more the first total is than the second total", "apply the provided definition exactly: Total of SMEs pay using Currency
  unit_and_scale: "currency amount; no percentage or scaling factor mentioned"
  ambiguities: ["whether 'pay' refers to the raw price field or a derived total from price and amount", "whether the result should be constrained to a specific sign or absolute difference"]
--- 最终 SQL ---
  SELECT SUM(CASE WHEN c.Currency = 'CZK' THEN t.Amount * t.Price ELSE 0 END) - SUM(CASE WHEN c.Currency = 'EUR' THEN t.Amount * t.Price ELSE 0 END) FROM customers AS c INNER JOIN transactions_1k AS t ON c.CustomerID = t.CustomerID WHERE c.Segment = 'SME'
--- gold SQL ---
  SELECT SUM(Currency = 'CZK') - SUM(Currency = 'EUR') FROM customers WHERE Segment = 'SME'
模型答: [[3332351.76]]
gold答: [[23505]]

### bird_1498   [未拦]
题面: What is the highest monthly consumption in the year 2012?
hint: 
--- 模型的分析 ---
  answer_shape: (无)
  counting_unit: (无)
  stated_conditions: (无)
  unit_and_scale: (无)
  ambiguities: (无)
--- 最终 SQL ---
  SELECT Consumption FROM yearmonth WHERE Date LIKE '2012%' ORDER BY Consumption DESC LIMIT 1
--- gold SQL ---
  SELECT SUM(Consumption) FROM yearmonth WHERE SUBSTR(Date, 1, 4) = '2012' GROUP BY SUBSTR(Date, 5, 2) ORDER BY SUM(Consumption) DESC LIMIT 1
模型答: [[445279.69]]
gold答: [[51787161.74]]

### bird_1529   [未拦]
题面: What is the amount spent by customer "38508" at the gas stations? How much had the customer spent in August 2012?
hint: 
--- 模型的分析 ---
  answer_shape: "Potentially one numeric value if the time reference is meant to narrow the spend amount, but the wording also allows two numeric values: total spent at gas stations overall and spent in August 2012."
  counting_unit: "Table rows are not being counted; the question asks for summed spending amount."
  stated_conditions: ["The customer is identified as 38508", "The spending is at gas stations", "August 2012 is defined by dates starting with 2012-08"]
  unit_and_scale: "The answer unit is monetary amount spent, in the same currency/units as the recorded amount values; no percentage or x100 scaling is involved."
  ambiguities: ["It is unclear whether the question asks for one total spent in August 2012 or two totals: overall gas-station spend and August 2012 spend", "It is unclear whether 'at the gas stations' is just context or a separate condition fro
--- 最终 SQL ---
  SELECT SUM(Amount * Price) FROM transactions_1k WHERE CustomerID = 38508 AND Date LIKE '2012-08%'
--- gold SQL ---
  SELECT SUM(Amount * Price) AS total_spent, SUM(CASE WHEN Date LIKE '2012-08%' THEN Amount * Price ELSE 0 END) AS august_2012_spent FROM transactions_1k WHERE CustomerID = 38508
模型答: [[88612.38]]
gold答: [[88612.38, 88612.38]]

### bird_173   [被拦过]
题面: How often does account number 3 request an account statement to be released? What was the aim of debiting 3539 in total?
hint: 
--- 模型的分析 ---
  answer_shape: "Two columns: one numeric result for how often account 3 requested an account statement to be released, and one text result for the purpose of the debit with total amount 3539."
  counting_unit: "Entities/transactions matching the statement-release purpose for account 3, counted as occurrences rather than raw rows if duplicates are possible."
  stated_conditions: ["account number 3", "request an account statement to be released", "debiting 3539 in total"]
  unit_and_scale: "The first part is a count; the second part is a purpose label (text), with no unit."
  ambiguities: ["It is unclear whether the 3539 total refers to a single payment amount or an aggregated total across multiple debits.", "It is unclear whether the statement-release request should be interpreted via the payment-purpose code for 
--- 被拦的 SQL ---
  SELECT (SELECT COUNT(*) FROM trans WHERE account_id = 3 AND k_symbol = 'SLUZBY') AS request_count, (SELECT k_symbol FROM "order" WHERE amount = 3539 LIMIT 1) AS purpose;
--- 最终 SQL ---
  SELECT (SELECT COUNT(DISTINCT trans_id) FROM trans WHERE account_id = 3 AND k_symbol = 'SLUZBY') AS request_count, (SELECT k_symbol FROM "order" WHERE amount = 3539 GROUP BY k_symbol ORDER BY COUNT(*) DESC, k_symbol LIMIT 1) AS aim;
--- gold SQL ---
  SELECT T1.frequency, T2.k_symbol FROM account AS T1 INNER JOIN (SELECT account_id, k_symbol, SUM(amount) AS total_amount FROM "order" GROUP BY account_id, k_symbol) AS T2 ON T1.account_id = T2.account_id WHERE T1.account_id = 3 AND T2.total_amount = 3539
模型答: [[13, "POJISTNE"]]
gold答: [["POPLATEK MESICNE", "POJISTNE"]]

### bird_226   [未拦]
题面: What is the percentage of double bonds in the molecule TR008? Please provide your answer as a percentage with five decimal places.
hint: 
--- 模型的分析 ---
  answer_shape: "Return one column: the percentage of double bonds in molecule TR008."
  counting_unit: "Bond records for the molecule; each bond row counts once."
  stated_conditions: ["The molecule is TR008.", "Double bonds are the bonds where bond_type = '='.", "The answer should be a percentage.", "The percentage should be reported with five decimal places."]
  unit_and_scale: "Percentage, so multiply the fraction by 100 before formatting."
  ambiguities: []
--- 最终 SQL ---
  SELECT printf('%.5f', CAST(SUM(bond_type = '=') AS REAL) * 100.0 / COUNT(bond_id)) FROM bond WHERE molecule_id = 'TR008';
--- gold SQL ---
  SELECT ROUND(CAST(COUNT(CASE WHEN T.bond_type = '=' THEN T.bond_id ELSE NULL END) AS REAL) * 100 / COUNT(T.bond_id),5) FROM bond AS T WHERE T.molecule_id = 'TR008'
模型答: [["3.84615"]]
gold答: [[3.84615]]

### bird_227   [被拦过]
题面: What is the percentage of molecules that are carcinogenic? Please provide your answer as a percentage with three decimal places.
hint: 
--- 模型的分析 ---
  answer_shape: "One column: the percentage of molecules that are carcinogenic."
  counting_unit: "Entities (molecules), not table rows; each molecule counts once."
  stated_conditions: ["Use molecules labeled '+' as carcinogenic.", "Compute percentage as DIVIDE(SUM(label = '+'), COUNT(molecule_id)) * 100.", "Return the answer as a percentage.", "Format the percentage with three decimal places."]
  unit_and_scale: "Percentage; multiply the fraction by 100 and present with three decimal places."
  ambiguities: []
--- 被拦的 SQL ---
  SELECT printf('%.3f', CAST(SUM(label = '+') AS REAL) / COUNT(molecule_id) * 100.0) AS percent FROM molecule;
--- 最终 SQL ---
  SELECT printf('%.3f', CAST(SUM(label = '+') AS REAL) / COUNT(DISTINCT molecule_id) * 100.0) AS percent FROM molecule;
--- gold SQL ---
  SELECT ROUND(CAST(COUNT(CASE WHEN T.label = '+' THEN T.molecule_id ELSE NULL END) AS REAL) * 100 / COUNT(T.molecule_id),3) FROM molecule t
模型答: [["44.315"]]
gold答: [[44.315]]

### bird_228   [未拦]
题面: How much of the hydrogen in molecule TR206 is accounted for? Please provide your answer as a percentage with four decimal places.
hint: 
--- 模型的分析 ---
  answer_shape: "One column containing a percentage value formatted to four decimal places."
  counting_unit: "Table rows/atoms in the specified molecule; the percentage is based on atom records for molecule TR206, with hydrogen atoms counted among those records."
  stated_conditions: ["The molecule id is TR206", "Hydrogen refers to element = 'h'", "The answer should be a percentage", "The percentage should be reported with four decimal places"]
  unit_and_scale: "Percentage; multiply the hydrogen fraction by 100 before formatting, with four decimal places."
  ambiguities: []
--- 最终 SQL ---
  SELECT printf('%.4f', 100.0 * SUM(element = 'h') / COUNT(atom_id)) AS percentage FROM atom WHERE molecule_id = 'TR206';
--- gold SQL ---
  SELECT ROUND(CAST(COUNT(CASE WHEN T.element = 'h' THEN T.atom_id ELSE NULL END) AS REAL) * 100 / COUNT(T.atom_id),4) FROM atom AS T WHERE T.molecule_id = 'TR206'
模型答: [["45.4545"]]
gold答: [[45.4545]]

### bird_24   [被拦过]
题面: Give the names of the schools with the percent eligible for free meals in K-12 is more than 0.1 and test takers whose test score is greater than or equal to 1500?
hint: 
--- 模型的分析 ---
  answer_shape: "Return one column: the school name."
  counting_unit: "Entities (schools), not table rows."
  stated_conditions: ["Include schools whose percent eligible for free meals in K-12 is more than 0.1.", "Use the definition percent eligible for free meals = free meal count in K-12 divided by total enrollment in K-12.", "Include schools with test ta
  unit_and_scale: "The free-meals condition is a proportion (not a percentage label unless converted); the threshold is 0.1 on that proportion scale, with no x100 conversion needed."
  ambiguities: ["The question does not explicitly say whether the SAT condition means at least one test taker scoring 1500+ or some other threshold on the count of such test takers.", "The question does not specify whether to use a distinct scho
--- 被拦的 SQL ---
  SELECT DISTINCT T1.[School Name] FROM frpm AS T1 INNER JOIN satscores AS T2 ON T2.cds = T1.CDSCode WHERE T1.[Free Meal Count (K-12)] * 1.0 / T1.[Enrollment (K-12)] > 0.1 AND T2.NumGE1500 > 0
--- 最终 SQL ---
  SELECT DISTINCT T1.[School Name] FROM frpm AS T1 INNER JOIN satscores AS T2 ON T2.cds = T1.CDSCode WHERE T1.[Free Meal Count (K-12)] * 1.0 / T1.[Enrollment (K-12)] > 0.1 AND T2.NumGE1500 > 0
--- gold SQL ---
  SELECT T2."School Name"
FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode 
WHERE CAST(T2."Free Meal Count (K-12)" AS REAL) / T2."Enrollment (K-12)" > 0.1 AND T1.NumGE1500 > 0 AND rtype = 'S'
模型答: [["FAME Public Charter"], ["Envision Academy for Arts & Technology"], ["Alameda Science and Technology Institute"], ["Alameda High"], ["Alternatives i
gold答: [["FAME Public Charter"], ["Envision Academy for Arts & Technology"], ["Alameda Science and Technology Institute"], ["Alameda High"], ["Alternatives i

### bird_26   [被拦过]
题面: State the names and full communication address of high schools in Monterey which has more than 800 free or reduced price meals for ages 5-17?
hint: 
--- 模型的分析 ---
  answer_shape: "2 columns: the school name, and its full communication address"
  counting_unit: "Entities (schools), not rows"
  stated_conditions: ["The schools must be high schools", "The schools must be in Monterey", "The schools must have more than 800 free or reduced price meals for ages 5-17", "The address must be the full communication address", "The full communication
  unit_and_scale: "The meal threshold is a raw count of meals (more than 800), not a percentage"
  ambiguities: ["Whether Monterey refers to the county or the city", "Whether 'communication address' means the physical address or the mailing address"]
--- 被拦的 SQL ---
  SELECT s.School AS school_name, CASE WHEN s.[Zip] IS NOT NULL AND s.[Zip] <> '' THEN s.[Street] || ', ' || s.[City] || ', ' || s.[State] || ' ' || s.[Zip] ELSE s.[Street] || ', ' || s.[City] || ', ' || s.[State] END AS full_communication_address FROM schools A
--- 最终 SQL ---
  SELECT DISTINCT s.School AS school_name, CASE WHEN s.Zip IS NOT NULL AND s.Zip <> '' THEN s.Street || ', ' || s.City || ', ' || s.State || ' ' || s.Zip ELSE s.Street || ', ' || s.City || ', ' || s.State END AS full_communication_address FROM schools AS s INNER JOIN frpm AS f ON s
--- gold SQL ---
  SELECT T1."School Name", T2.Street, T2.City, T2.State, T2.Zip
FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode 
WHERE T2.County = 'Monterey' AND T1."FRPM Count (Ages 5-17)" > 800 AND T1."School Type" = 'High Schools (Public)' AND T2.School is not NULL
模型答: [["Alisal High", "777 Williams Road, Salinas, CA 93905-1907"], ["Everett Alvarez High", "1900 Independence Boulevard, Salinas, CA 93906-5300"], ["Nort
gold答: [["Alisal High", "777 Williams Road", "Salinas", "CA", "93905-1907"], ["Everett Alvarez High", "1900 Independence Boulevard", "Salinas", "CA", "93906-

### bird_273   [未拦]
题面: What is the percentage of element chlorine in carcinogenic molecules?
hint: 
--- 模型的分析 ---
  answer_shape: "One numeric column giving the percentage of chlorine among atoms in carcinogenic molecules."
  counting_unit: "Table rows representing atoms; identical atom rows count separately because the hint defines percentage as SUM(element = 'cl') / COUNT(element) over carcinogenic molecules."
  stated_conditions: ["Consider only molecules whose label is '+'", "Chlorine is the element code 'cl'", "Compute percentage as SUM(element = 'cl') divided by COUNT(element)"]
  unit_and_scale: "Percentage; the ratio should be expressed as a percent, so multiply the fraction by 100 if needed."
  ambiguities: ["Whether the result should be returned as a fraction or already multiplied by 100", "Whether the percentage is over all atoms in carcinogenic molecules or over all molecules containing chlorine; the hint specifies atoms"]
--- 最终 SQL ---
  SELECT CAST(SUM(CASE WHEN a.element = 'cl' THEN 1 ELSE 0 END) AS REAL) / COUNT(a.element) * 100 AS percentage FROM atom AS a INNER JOIN molecule AS m ON a.molecule_id = m.molecule_id WHERE m.label = '+';
--- gold SQL ---
  SELECT CAST(COUNT( CASE WHEN T1.element = 'cl' THEN T1.element ELSE NULL END) AS REAL) * 100 / COUNT(T1.element) FROM atom AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id WHERE T2.label = '+'
模型答: [[3.14192849404117]]
gold答: [[3.1419284940411703]]

### bird_352   [被拦过]
题面: Calculate the percentage of the cards availabe in Chinese Simplified.
hint: 
--- 模型的分析 ---
  answer_shape: "One numeric column giving the percentage of cards available in Chinese Simplified."
  counting_unit: "Table rows / ids, not distinct entities."
  stated_conditions: ["Use Chinese Simplified as the language filter.", "Compute percentage as Sum(id where language = 'Chinese Simplified') divided by Count(id), then multiply by 100."]
  unit_and_scale: "Percentage; multiply by 100."
  ambiguities: []
--- 被拦的 SQL ---
  SELECT CAST(SUM(CASE WHEN language = 'Chinese Simplified' THEN id ELSE 0 END) AS REAL) * 100.0 / COUNT(id) FROM set_translations
--- 最终 SQL ---
  SELECT CAST(COUNT(DISTINCT CASE WHEN st.language = 'Chinese Simplified' THEN s.code END) AS REAL) * 100.0 / COUNT(DISTINCT s.code) FROM sets AS s LEFT JOIN set_translations AS st ON st.setCode = s.code /* setCode repeats across language rows, so DISTINCT counts each set/card enti
--- gold SQL ---
  SELECT CAST(COUNT(DISTINCT CASE WHEN T2.language = 'Chinese Simplified' THEN T1.id ELSE NULL END) AS REAL) * 100 / COUNT(DISTINCT T1.id) FROM cards AS T1 LEFT JOIN foreign_data AS T2 ON T1.uuid = T2.uuid
模型答: [[21.960072595281307]]
gold答: [[35.384182182957304]]

### bird_36   [未拦]
题面: Under whose administration is the school with the highest number of students scoring 1500 or more on the SAT? Indicate their full names.
hint: 
--- 模型的分析 ---
  answer_shape: "Return the full names of the administrator(s): first name and last name, so two columns."
  counting_unit: "Entities/schools, not table rows; the question is about the school with the highest number of qualifying SAT students."
  stated_conditions: ["Find the school with the highest number of students scoring 1500 or more on the SAT", "Use NumGE1500 for SAT scores greater than or equal to 1500", "Indicate the full names of the administrator(s)", "Full name means first name a
  unit_and_scale: "The answer is not a percentage; it is a school-level maximum based on the count of qualifying SAT test takers."
  ambiguities: ["If multiple schools tie for the highest NumGE1500, the question does not say how to break the tie", "It is not explicit whether to return one administrator or all administrators for the top school, though the hint allows up to 3
--- 最终 SQL ---
  WITH top_school AS ( SELECT cds FROM satscores ORDER BY NumGE1500 DESC LIMIT 1 ) SELECT sch.AdmFName1, sch.AdmLName1 FROM schools AS sch JOIN top_school AS t ON sch.CDSCode = t.cds WHERE sch.AdmFName1 IS NOT NULL AND sch.AdmLName1 IS NOT NULL UNION ALL SELECT sch.AdmFName2, sch.A
--- gold SQL ---
  SELECT s.AdmFName1,
       s.AdmLName1,
       s.AdmFName2,
       s.AdmLName2,
       s.AdmFName3,
       s.AdmLName3
FROM satscores t
JOIN schools  s ON t.cds = s.CDSCode
WHERE t.rtype = 'S'    
ORDER BY t.NumGE1500 DESC
LIMIT 1;
模型答: [["Michelle", "King"]]
gold答: [["Andrew", "Ishibashi", null, null, null, null]]

### bird_407   [未拦]
题面: Lists all types of cards in German.
hint: 
--- 模型的分析 ---
  answer_shape: "One column: the German card type value(s) requested by the question."
  counting_unit: "Not counting; this is a listing question, so duplicates should be removed if present."
  stated_conditions: ["The language is German", "Only cards with all types are included", "Subtypes is not null", "Supertypes is not null"]
  unit_and_scale: "Text values; no percentage or numeric scaling"
  ambiguities: ["Whether 'types' means the combined card type text or the distinct subtype/supertype values", "Whether the result should include all matching rows or only unique type values"]
--- 最终 SQL ---
  SELECT DISTINCT T1.type FROM foreign_data AS T1 INNER JOIN cards AS T2 ON T1.uuid = T2.uuid WHERE T1.language = 'German' AND T2.subtypes IS NOT NULL AND T2.supertypes IS NOT NULL ORDER BY T1.type;
--- gold SQL ---
  SELECT T1.subtypes, T1.supertypes FROM cards AS T1 INNER JOIN foreign_data AS T2 ON T1.uuid = T2.uuid WHERE T2.language = 'German' AND T1.subtypes IS NOT NULL AND T1.supertypes IS NOT NULL
模型答: [[""], ["Artefaktkreatur — Golem, Legende"], ["Artefaktkreatur — Zauberer, Legende"], ["Beschwörung einer Legende"], ["Kreatur — Atog, Legende"], ["Kr
gold答: [["Human,Rebel", "Legendary"], ["Angel", "Legendary"], ["Merfolk,Wizard", "Legendary"], ["Vampire,Noble", "Legendary"], ["Avatar,Minion", "Legendary"]

### bird_465   [未拦]
题面: Which sets of cards with "Ancestor's Chosen" in it have a Korean version?
hint: 
--- 模型的分析 ---
  answer_shape: "Return one column: the set code(s) for sets that have a card named Ancestor's Chosen with a Korean version."
  counting_unit: "Sets, not rows; if multiple matching card printings exist in the same set, that set should appear once."
  stated_conditions: ["The card name is Ancestor's Chosen", "The version language is Korean"]
  unit_and_scale: "Set codes; no percentage or scaling is involved."
  ambiguities: []
--- 最终 SQL ---
  SELECT DISTINCT sets.name FROM cards INNER JOIN foreign_data ON foreign_data.uuid = cards.uuid INNER JOIN sets ON cards.setCode = sets.code WHERE cards.name = 'Ancestor''s Chosen' AND foreign_data.language = 'Korean';
--- gold SQL ---
  SELECT DISTINCT T3.name FROM cards AS T1 INNER JOIN set_translations AS T2 ON T2.setCode = T1.setCode INNER JOIN sets AS T3 ON T3.code = T1.setCode WHERE T1.name = 'Ancestor''s Chosen' AND T2.language = 'Korean'
模型答: []
gold答: [["Tenth Edition"], ["Judgment"]]

### bird_48   [未拦]
题面: What is the ratio of merged Unified School District schools in Orange County to merged Elementary School District schools?
hint: 
--- 模型的分析 ---
  answer_shape: "one numeric column giving the ratio of the count of merged Unified School District schools in Orange County divided by the count of merged Elementary School District schools"
  counting_unit: "schools"
  stated_conditions: ["count only schools in Orange County", "use the Unified School District definition for the numerator", "use the Elementary School District definition for the denominator", "compute the ratio as numerator count divided by denomina
  unit_and_scale: "unitless ratio; no percentage scaling required"
  ambiguities: ["what field or rule identifies a school as merged", "whether Orange County refers to the school county or the district county", "whether the counts should be distinct schools or raw rows if duplicates exist"]
--- 最终 SQL ---
  SELECT 1.0 * SUM(CASE WHEN County = 'Orange' AND StatusType = 'Merged' AND DOC = '54' THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN County = 'Orange' AND StatusType = 'Merged' AND DOC = '52' THEN 1 ELSE 0 END), 0) FROM schools;
--- gold SQL ---
  SELECT CAST((
SELECT COUNT(*) FROM schools 
WHERE County = 'Orange' AND DOC = '54' AND StatusType = 'Merged' AND school is not null) AS REAL) 
/ (SELECT COUNT(*) FROM schools WHERE DOC = '52' AND StatusType = 'Merged' AND school is not null) AS ratio;
模型答: [[0.5714285714285714]]
gold答: [[0.010958904109589041]]

### bird_50   [未拦]
题面: What is the postal street address for the school with the 7th highest Math average? Indicate the school's name.
hint: 
--- 模型的分析 ---
  answer_shape: "Return 2 columns: the school's name and its postal street address."
  counting_unit: "Not counting entities or table rows; the question asks for a single ranked school record."
  stated_conditions: ["Find the school with the 7th highest Math average.", "Include the school's name.", "Provide the postal street address."]
  unit_and_scale: "The ranking is by Math average value itself; no percentage conversion is involved."
  ambiguities: ["Whether ties in Math average should be handled as a simple 7th row after sorting or as the 7th distinct value.", "Whether the postal street address should be the full mailing street text or an abbreviated form."]
--- 最终 SQL ---
  SELECT schools.School, schools.MailStreet FROM schools INNER JOIN satscores ON schools.CDSCode = satscores.cds WHERE satscores.AvgScrMath IS NOT NULL ORDER BY satscores.AvgScrMath DESC LIMIT 1 OFFSET 6
--- gold SQL ---
  SELECT s.`MailStreet`   AS postal_street_address,
       s.`School`
FROM   `satscores` AS ss
JOIN   `schools`   AS s
       ON ss.`cds` = s.`CDSCode`
WHERE  ss.`rtype` = 'S'
  AND  ss.`AvgScrMath` IS NOT NULL
ORDER BY ss.`AvgScrMath` DESC
LIMIT 6, 1;
模型答: [[null, "25 Churchill Avenue"]]
gold答: [["5172 Orange Avenue", "Oxford Academy"]]

### bird_587   [未拦]
题面: For each post tagged 'humor', list the title, the comment, and the overall average view count across all posts tagged 'humor'.
hint: 
--- 模型的分析 ---
  answer_shape: "3 columns: post title, post comment/text, and the overall average view count for the tagged posts (the same average value on each returned row)"
  counting_unit: "entities (posts), not table rows"
  stated_conditions: ["Include only posts tagged '<humor>'", "For each such post, return its title", "For each such post, return its comment/text", "Also include the overall average view count across all posts tagged '<humor>'", "Use the given definit
  unit_and_scale: "Average view count is measured in raw view counts; no percentage and no x100 scaling"
  ambiguities: ["The exact source/version of the post comment/text is not fully specified if a post has multiple text revisions", "It is unclear whether the average should be returned as a repeated value alongside each post row or as a separate 
--- 最终 SQL ---
  SELECT p.Title, c.Text AS Comment, (SELECT AVG(ViewCount) FROM posts WHERE Tags LIKE '%<humor>%') AS avg_view_count FROM posts p JOIN comments c ON c.PostId = p.Id WHERE p.Tags LIKE '%<humor>%'
--- gold SQL ---
  SELECT p.Title, c.Text AS Comment, ( 
SELECT AVG(ViewCount) 
FROM posts WHERE Tags LIKE '<humor>' ) AS AverageViewCount 
FROM posts AS p JOIN comments AS c ON p.Id = c.PostId WHERE p.Tags = '<humor>'
模型答: [["So how many staticians *does* it take to screw in a lightbulb?", "Probably better asked on meta.  People feel like they have to downvote it because
gold答: [["So how many staticians *does* it take to screw in a lightbulb?", "Probably better asked on meta.  People feel like they have to downvote it because

### bird_604   [被拦过]
题面: What is the average of the up votes and the average user age for users creating more than 10 posts?
hint: 
--- 模型的分析 ---
  answer_shape: "Return 2 columns: the average up votes and the average user age."
  counting_unit: "Users (people), not table rows; only users who meet the post-creation threshold are included."
  stated_conditions: ["Include only users creating more than 10 posts.", "Treat creating more than 10 posts as Count(UserId) > 10.", "Compute the average of the up votes as Sum(UpVotes) divided by Count(UserId).", "Compute the average age as Sum(Age) 
  unit_and_scale: "Both outputs are averages in the same units as the underlying fields: up-vote counts and years of age. No percentage or x100 conversion is needed."
  ambiguities: ["Whether \"creating posts\" should be interpreted as all posts or only a specific post type is not stated explicitly.", "The exact grouping key for counting posts is implied by the hint but not otherwise described."]
--- 被拦的 SQL ---
  SELECT CAST(SUM(T1.UpVotes) AS REAL) / COUNT(T1.Id), CAST(SUM(T1.Age) AS REAL) / COUNT(T1.Id) FROM users AS T1 INNER JOIN ( SELECT T2.OwnerUserId FROM posts AS T2 WHERE T2.OwnerUserId IS NOT NULL GROUP BY T2.OwnerUserId HAVING COUNT(T2.OwnerUserId) > 10 ) AS T
--- 最终 SQL ---
  SELECT CAST(SUM(T1.UpVotes) AS REAL) / COUNT(DISTINCT T1.Id), CAST(SUM(T1.Age) AS REAL) / COUNT(DISTINCT T1.Id) FROM users AS T1 INNER JOIN ( SELECT T2.OwnerUserId FROM posts AS T2 WHERE T2.OwnerUserId IS NOT NULL GROUP BY T2.OwnerUserId HAVING COUNT(T2.OwnerUserId) > 10 ) AS T3 
--- gold SQL ---
  SELECT AVG(T1.UpVotes), AVG(T1.Age) FROM users AS T1 INNER JOIN ( SELECT OwnerUserId, COUNT(*) AS post_count FROM posts GROUP BY OwnerUserId HAVING post_count > 10) AS T2 ON T1.Id = T2.OwnerUserId
模型答: [[182.2832618025751, 9.127896995708154]]
gold答: [[182.2832618025751, 34.083333333333336]]

### bird_637   [未拦]
题面: State all the tags used by Mark Meckes in his posts that doesn't have comments.
hint: 
--- 模型的分析 ---
  answer_shape: "One column listing the tag names."
  counting_unit: "Not a counting question; it asks for a list of tags, so repeated tag values should be treated as the same tag if they appear multiple times."
  stated_conditions: ["The relevant person is Mark Meckes.", "Only posts by that person are relevant.", "The posts must have no comments.", "Null tags must be excluded."]
  unit_and_scale: "Tag names as text; no numeric scaling applies."
  ambiguities: ["Whether 'all the tags' should be distinct tag values or preserve duplicates if the same tag appears in multiple qualifying posts.", "Whether 'in his posts' refers to posts authored by Mark Meckes rather than posts merely associa
--- 最终 SQL ---
  WITH RECURSIVE split(tag, rest) AS ( SELECT substr(p.Tags, 2, instr(substr(p.Tags, 2), '>') - 1) AS tag, substr(p.Tags, instr(substr(p.Tags, 2), '>') + 2) AS rest FROM posts AS p INNER JOIN users AS u ON p.OwnerUserId = u.Id WHERE u.DisplayName = 'Mark Meckes' AND p.CommentCount 
--- gold SQL ---
  SELECT DISTINCT p.`Tags`
FROM `posts` p
JOIN `users` u ON u.`Id` = p.`OwnerUserId`
WHERE u.`DisplayName` = 'Mark Meckes'
  AND p.`CommentCount` = 0
  AND p.`Tags` IS NOT NULL;
模型答: [["books"]]
gold答: [["<books>"]]

### bird_640   [未拦]
题面: Calculate the difference in view count from post posted by Mornington and view count from posts posted by Amos.
hint: 
--- 模型的分析 ---
  answer_shape: "One column containing a single numeric difference value."
  counting_unit: "Table rows aggregated by post owner name, with all matching records for each named person summed before subtraction."
  stated_conditions: ["One side of the calculation is the sum of view counts for posts associated with Mornington.", "The other side of the calculation is the sum of view counts for posts associated with Amos.", "The required output is the difference 
  unit_and_scale: "View count units; no percentage or scaling is required."
  ambiguities: ["It is not fully explicit whether the name matching should use the post owner display name field or another display name field, but the hint specifies DisplayName.", "The question does not specify whether missing view counts shou
--- 最终 SQL ---
  SELECT SUM(CASE WHEN OwnerDisplayName = 'Mornington' THEN ViewCount ELSE 0 END) - SUM(CASE WHEN OwnerDisplayName = 'Amos' THEN ViewCount ELSE 0 END) FROM posts;
--- gold SQL ---
  SELECT SUM(CASE WHEN u.DisplayName = 'Mornington' THEN p.ViewCount ELSE 0 END) - SUM(CASE WHEN u.DisplayName = 'Amos' THEN p.ViewCount ELSE 0 END) FROM posts p JOIN users u ON p.OwnerUserId = u.Id WHERE u.DisplayName IN ('Mornington', 'Amos') AND p.ViewCount IS NOT NULL;
模型答: [[0]]
gold答: [[-497]]

### bird_750   [未拦]
题面: What is the average weight of all female superheroes?
hint: 
--- 模型的分析 ---
  answer_shape: "One column: the average weight of the matching superheroes."
  counting_unit: "Not counting entities or rows; this is an aggregate average over all matching superhero records."
  stated_conditions: ["Only female superheroes are included", "female means gender = 'Female'", "average weight means AVG(weight_kg)"]
  unit_and_scale: "Weight is in kilograms; the answer is an average in kilograms, no x100 conversion."
  ambiguities: ["Whether superheroes with missing weight values should be excluded is not stated explicitly, though AVG typically ignores NULLs", "Whether zero weights should be treated as valid values or as missing is not stated"]
--- 最终 SQL ---
  SELECT AVG(s.weight_kg) FROM superhero AS s INNER JOIN gender AS g ON s.gender_id = g.id WHERE g.gender = 'Female';
--- gold SQL ---
  SELECT AVG(weight_kg) FROM superhero s JOIN gender g ON s.gender_id = g.id WHERE g.gender = 'Female' AND weight_kg > 0;
模型答: [[60.77956989247312]]
gold答: [[78.50694444444444]]

### bird_791   [未拦]
题面: Calculate the average height for all superhero.
hint: 
--- 模型的分析 ---
  answer_shape: "One numeric column containing the average height."
  counting_unit: "Not a count; the question asks for an average across all superheroes."
  stated_conditions: ["Use all superheroes", "Calculate the average height"]
  unit_and_scale: "Height is in centimeters, so the answer should be in centimeters with no x100 conversion."
  ambiguities: ["Whether missing or zero height values should be excluded or treated as missing data"]
--- 最终 SQL ---
  SELECT AVG(height_cm) FROM superhero;
--- gold SQL ---
  SELECT AVG(height_cm) FROM superhero WHERE height_cm > 0;
模型答: [[267.7514450867052]]
gold答: [[345.03538175046555]]

### bird_85   [被拦过]
题面: What is the Percent (%) Eligible Free (K-12) in the school administered by an administrator whose first name is Alusine. List the district code of the school.
hint: 
--- 模型的分析 ---
  answer_shape: "Two columns: the Percent (%) Eligible Free (K-12) value and the district code of the school."
  counting_unit: "Not a counting question; it asks for the matching school record(s), not rows or entities to be counted."
  stated_conditions: ["Find the school administered by an administrator whose first name is Alusine.", "Use Percent (%) Eligible Free (K-12) as Free Meal Count (K-12) divided by Enrollment (K-12) times 100%.", "List the district code of the school."]
  unit_and_scale: "The answer is a percentage, on a 0-100 scale, so the ratio must be multiplied by 100."
  ambiguities: ["There may be more than one school whose administrator has the first name Alusine.", "It is unclear whether the requested percent should be taken directly from a stored field or computed from the two counts, though the hint defin
--- 被拦的 SQL ---
  SELECT f.`Free Meal Count (K-12)` / NULLIF(f.`Enrollment (K-12)`, 0) * 100.0, f.`District Code` FROM schools AS s JOIN frpm AS f ON s.CDSCode = f.CDSCode WHERE s.AdmFName1 = 'Alusine'
--- 最终 SQL ---
  SELECT f.`Free Meal Count (K-12)` / NULLIF(f.`Enrollment (K-12)`, 0) * 100.0, f.`District Code` FROM schools AS s JOIN frpm AS f ON s.CDSCode = f.CDSCode WHERE s.AdmFName1 = 'Alusine'
--- gold SQL ---
  SELECT T1."Free Meal Count (K-12)" * 100 / T1."Enrollment (K-12)", T1."District Code" FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.AdmFName1 = 'Alusine'
模型答: [[70.15113350125944, 64857]]
gold答: [[70.15113350125945, 64857]]

### bird_881   [未拦]
题面: For the drivers who took part in the race in 1983/7/16, what's their race completion rate?
hint: 
--- 模型的分析 ---
  answer_shape: "Return 1 column: the race completion rate as a percentage."
  counting_unit: "Drivers (the drivers who took part in the specified race)."
  stated_conditions: ["The race date is 1983-07-16.", "A driver counts as completed if their status is Finished.", "A driver also counts as completed if their status matches +% Lap%."]
  unit_and_scale: "Percentage; multiply the completion fraction by 100."
  ambiguities: []
--- 最终 SQL ---
  SELECT CAST(COUNT(CASE WHEN status.status = 'Finished' OR status.status LIKE '+% Lap%' THEN results.driverId END) AS REAL) / COUNT(results.driverId) * 100 AS percentage FROM results JOIN races ON results.raceId = races.raceId JOIN status ON results.statusId = status.statusId WHER
--- gold SQL ---
  SELECT 100.0 * SUM(CASE
                     WHEN s.`status` = 'Finished'
                          OR s.`status` LIKE '+% Lap%'
                   THEN 1 ELSE 0 END) / COUNT(*) AS completion_rate
FROM `races` r
JOIN `results` res ON res.`raceId` = r.`raceId`
JOIN `status`  s   O
模型答: [[58.620689655172406]]
gold答: [[58.62068965517241]]

### bird_894   [未拦]
题面: What is the best lap time recorded? List the recorded lap time, driver, and race.
hint: 
--- 模型的分析 ---
  answer_shape: "Return 3 columns: the recorded lap time, the driver name as forename plus surname, and the race name."
  counting_unit: "Not counting entities; this asks for the single row associated with the minimum lap time record."
  stated_conditions: ["Find the best lap time recorded.", "Use the lap time definition as min(milliseconds).", "List the driver using forename and surname.", "List the race using race name."]
  unit_and_scale: "The answer’s lap time is in milliseconds because best lap time is defined as min(milliseconds); no percentage or scaling is needed."
  ambiguities: ["Whether ties for the minimum lap time should all be returned or only one record."]
--- 最终 SQL ---
  SELECT lapTimes.time AS lap_time, drivers.forename, drivers.surname, races.name AS race FROM lapTimes JOIN drivers ON lapTimes.driverId = drivers.driverId JOIN races ON lapTimes.raceId = races.raceId ORDER BY lapTimes.milliseconds ASC LIMIT 1
--- gold SQL ---
  SELECT T2.milliseconds, T1.forename, T1.surname, T3.name FROM drivers AS T1 INNER JOIN lapTimes AS T2 ON T1.driverId = T2.driverId INNER JOIN races AS T3 ON T2.raceId = T3.raceId ORDER BY T2.milliseconds ASC LIMIT 1
模型答: [["1:07.411", "Lewis", "Hamilton", "Austrian Grand Prix"]]
gold答: [[67411, "Lewis", "Hamilton", "Austrian Grand Prix"]]

### bird_928   [未拦]
题面: Which driver ranked the first in the Canadian Grand Prix in 2007? Please give his forename, surname, and reference name.
hint: 
--- 模型的分析 ---
  answer_shape: "Return 3 columns: the driver's forename, surname, and reference name."
  counting_unit: "Not counting entities; the question asks for a single driver, so no aggregation is needed."
  stated_conditions: ["The race is the Canadian Grand Prix", "The year is 2007", "The driver ranked first"]
  unit_and_scale: "The rank is an ordinal race position, with first meaning position 1; no percentage or other scaling applies."
  ambiguities: ["Whether 'ranked the first' refers to the race finishing position or another ranking field, though the race-result interpretation is the natural one."]
--- 最终 SQL ---
  SELECT d.forename, d.surname, d.driverRef FROM results AS r INNER JOIN races AS ra ON r.raceId = ra.raceId INNER JOIN drivers AS d ON r.driverId = d.driverId WHERE ra.name = 'Canadian Grand Prix' AND ra.year = 2007 ORDER BY r.position ASC LIMIT 1
--- gold SQL ---
  SELECT d.forename, d.surname, d.driverRef FROM drivers AS d JOIN results AS r ON d.driverId = r.driverId JOIN races AS ra ON r.raceId = ra.raceId WHERE ra.name = 'Canadian Grand Prix' AND ra.year = 2007 AND r.position = 1
模型答: [["Jarno", "Trulli", "trulli"]]
gold答: [["Lewis", "Hamilton", "hamilton"]]

### bird_931   [未拦]
题面: What was the fastest lap speed among all drivers in the 2009 Spanish Grand Prix?
hint: 
--- 模型的分析 ---
  answer_shape: "Return 1 column: the maximum fastest lap speed among all drivers in the 2009 Spanish Grand Prix."
  counting_unit: "Not counting entities; the question asks for a single aggregated value, not rows or distinct drivers."
  stated_conditions: ["Consider the 2009 Spanish Grand Prix", "Use fastest lap speed among all drivers", "Take the maximum fastest lap speed"]
  unit_and_scale: "The answer is in the fastest-lap-speed unit, which is kilometers per hour (km/h); no percentage conversion is involved."
  ambiguities: []
--- 最终 SQL ---
  SELECT CAST(r.fastestLapSpeed AS REAL) FROM results AS r JOIN races AS ra ON ra.raceId = r.raceId WHERE ra.year = 2009 AND ra.name = 'Spanish Grand Prix' ORDER BY CAST(r.fastestLapSpeed AS REAL) DESC LIMIT 1
--- gold SQL ---
  SELECT T2.fastestLapSpeed FROM races AS T1 INNER JOIN results AS T2 ON T2.raceId = T1.raceId WHERE T1.name = 'Spanish Grand Prix' AND T1.year = 2009 AND T2.fastestLapSpeed IS NOT NULL ORDER BY T2.fastestLapSpeed DESC LIMIT 1
模型答: [[202.484]]
gold答: [["202.484"]]
