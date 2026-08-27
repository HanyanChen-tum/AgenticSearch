### bird_1028  [confident_miss]  基线 run1=错 run2=错
题面: In Scotland Premier League, which away team won the most during the 2010 season?
形状: 模型 1行×1列 / gold 2行×1列
模型SQL: SELECT T.team_long_name FROM Team AS T JOIN (SELECT M.away_team_api_id FROM Match AS M JOIN League AS L ON M.league_id = L.id WHERE L.name = 'Scotland Premier League' AND M.season = '2009/2010' AND M.away_team_goal > M.home_team_goal GROUP BY M.away_team_api_id ORDER BY COUNT(*) DESC LIMIT 1) AS X O
goldSQL: SELECT DISTINCT t.team_long_name FROM Team t JOIN Match m ON t.team_api_id = m.away_team_api_id JOIN League l ON m.league_id = l.id WHERE l.name = 'Scotland Premier League' AND m.season = '2009/2010' AND m.away_team_goal > m.home_team_goal GROUP BY t.team_api_id, t.team_long_name HAVING COUNT(*) = (
模型答: [["Celtic"]]
gold答: [["Rangers"], ["Celtic"]]

### bird_1032  [confident_miss]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后判对
题面: Give the name of the league with the highest matches of all time and how many matches were played in the said league.
形状: 模型 1行×2列 / gold 3行×2列
模型SQL: SELECT League.name, COUNT(Match.league_id) AS matches FROM Match JOIN League ON Match.league_id = League.id GROUP BY League.id, League.name ORDER BY COUNT(Match.league_id) DESC LIMIT 1;
goldSQL: SELECT l.name, COUNT(m.id) AS match_count FROM League AS l JOIN Match AS m ON l.id = m.league_id GROUP BY l.id, l.name HAVING COUNT(m.id) = (SELECT MAX(match_count) FROM (SELECT COUNT(id) AS match_count FROM Match GROUP BY league_id ) )
模型答: [["England Premier League", 3040]]
gold答: [["England Premier League", 3040], ["France Ligue 1", 3040], ["Spain LIGA BBVA", 3040]]

### bird_1037  [phase_a_other]  基线 run1=错 run2=对
题面: Calculate the percentage of players who prefer the left foot at least once across all available season records and were born between 1987 and 1992.
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT 100.0 * SUM(pa.preferred_foot = 'left') / COUNT(pa.player_fifa_api_id) AS percentage FROM Player_Attributes AS pa INNER JOIN Player AS p ON pa.player_fifa_api_id = p.player_fifa_api_id WHERE CAST(substr(p.birthday, 1, 4) AS INTEGER) BETWEEN 1987 AND 1992;
goldSQL: SELECT CAST(COUNT(DISTINCT CASE WHEN t2.preferred_foot = 'left' THEN t1.id ELSE NULL END) AS REAL) * 100 / COUNT(DISTINCT t1.id) percent FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_api_id = t2.player_api_id WHERE SUBSTR(t1.birthday, 1, 4) BETWEEN '1987' AND '1992'
模型答: [[24.561269355763717]]
gold答: [[28.868144690781797]]

### bird_1068  [phase_a_other]  基线 run1=错 run2=错
题面: From 2010 to 2015, what was the average overall rating of players who are higher than 170?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT SUM(t2.overall_rating) / COUNT(t2.id) AS average_overall_rating FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_api_id = t2.player_api_id WHERE strftime('%Y', t2.date) >= '2010' AND strftime('%Y', t2.date) <= '2015' AND t1.height > 170
goldSQL: SELECT AVG(t2.overall_rating) AS avg_rating
FROM `Player` AS t1
JOIN `Player_Attributes` AS t2 ON t1.player_api_id = t2.player_api_id
WHERE t1.height > 170
  AND strftime('%Y', t2.`date`) BETWEEN '2010' AND '2015';
模型答: [[68]]
gold答: [[68.90135724487692]]

### bird_1080  [phase_a_other]  基线 run1=对 run2=对
题面: Among players who prefer using their left foot when attacking, how many have at least one record indicating they would stay in their position while the team attacked?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT COUNT(DISTINCT player_api_id) FROM Player_Attributes WHERE preferred_foot = 'left' AND attacking_work_rate = 'low';
goldSQL: SELECT COUNT(DISTINCT player_api_id) FROM Player_Attributes WHERE preferred_foot = 'left' AND attacking_work_rate = 'low'
模型答: [[189]]
gold答: [[189]]

### bird_1149  [phase_a_other]  基线 run1=错 run2=错
题面: Among male patients, what is the ratio of in-patients to outpatients?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT CAST(SUM(CASE WHEN SEX = 'M' AND Admission = '+' THEN 1 ELSE 0 END) AS REAL) / SUM(CASE WHEN SEX = 'M' AND Admission = '-' THEN 1 ELSE 0 END) FROM Patient
goldSQL: SELECT CAST(SUM(CASE WHEN Admission = '+' THEN 1 ELSE 0 END) AS REAL) * 100 / SUM(CASE WHEN Admission = '-' THEN 1 ELSE 0 END) FROM Patient WHERE SEX = 'M'
模型答: [[0.8317757009345794]]
gold答: [[83.17757009345794]]

### bird_1169  [phase_a_other]  基线 run1=错 run2=错
题面: What is the ratio of male to female patients among all those with abnormal uric acid counts?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT CAST(SUM(CASE WHEN P.SEX = 'M' AND L.UA <= 8.0 THEN 1 ELSE 0 END) AS REAL) / NULLIF(SUM(CASE WHEN P.SEX = 'F' AND L.UA <= 6.5 THEN 1 ELSE 0 END), 0) AS ratio FROM Laboratory AS L INNER JOIN Patient AS P ON L.ID = P.ID;
goldSQL: SELECT CAST(COUNT(DISTINCT CASE WHEN T2.UA <= 8.0 AND T1.SEX = 'M' THEN T1.ID ELSE NULL END) AS REAL) / COUNT(DISTINCT CASE WHEN T2.UA <= 6.5 AND T1.SEX = 'F' THEN T1.ID ELSE NULL END) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID
模型答: [[0.20566810835419985]]
gold答: [[0.184]]

### bird_1235  [confident_miss]  基线 run1=对 run2=错
题面: What are the diagnoses of patients who have at least one record indicating a low red blood cell count? Please list each patient’s ID and age.
形状: 模型 73行×3列 / gold 73行×3列
模型SQL: SELECT DISTINCT P.Diagnosis, P.ID, (CAST(strftime('%Y', current_timestamp) AS INTEGER) - CAST(strftime('%Y', P.Birthday) AS INTEGER) - (strftime('%m%d', current_timestamp) < strftime('%m%d', P.Birthday))) AS age FROM Patient AS P INNER JOIN Laboratory AS L ON P.ID = L.ID WHERE L.RBC < 3.5
goldSQL: SELECT DISTINCT T1.Diagnosis, T1.ID , STRFTIME('%Y', CURRENT_TIMESTAMP) - STRFTIME('%Y', T1.Birthday) - CASE
    WHEN strftime('%m-%d','now') < strftime('%m-%d', Birthday) THEN 1
    ELSE 0
  END AS age
 FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T2.RBC < 3.5
模型答: [["RA, SLE susp", 27654, 90], ["SLE, MCTD", 30609, 82], ["SJS", 58139, 53], ["RA", 71417, 96], ["RA", 130370, 73], ["MRA", 444499,
gold答: [["RA, SLE susp", 27654, 90], ["SLE, MCTD", 30609, 82], ["SJS", 58139, 53], ["RA", 71417, 96], ["RA", 130370, 73], ["MRA", 444499,

### bird_1241  [phase_a_other]  基线 run1=错 run2=错
题面: For patients with abnormal platelet level, what is the difference between the number of patients with lower than normal range and the number of patients with higher than normal range?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT SUM(PLT < 100) - SUM(PLT > 400) AS difference FROM Laboratory;
goldSQL: SELECT COUNT(DISTINCT CASE WHEN T2.PLT < 100 THEN T1.id END) - COUNT(DISTINCT CASE WHEN T2.PLT > 400 THEN T1.id END) FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID
模型答: [[-555]]
gold答: [[-46]]

### bird_1243  [phase_a_other]  基线 run1=错 run2=错
题面: For all patients who are older than 55 years old, what percentage of those with at least one record indicating an abnormal prothrombin time (PT) are female?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT CAST(SUM(CASE WHEN p.SEX = 'F' AND l.PT >= 14 THEN 1 ELSE 0 END) AS REAL) * 100.0 / SUM(CASE WHEN l.PT >= 14 THEN 1 ELSE 0 END) FROM Patient AS p INNER JOIN Laboratory AS l ON p.ID = l.ID WHERE datetime(p.Birthday, '+55 years') < current_timestamp
goldSQL: SELECT CAST(COUNT(DISTINCT CASE WHEN T2.PT >= 14 AND T1.SEX = 'F' THEN T1.ID END) AS REAL) * 100 / COUNT(DISTINCT CASE WHEN T2.PT >= 14 THEN T1.ID END) 
FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE date(Birthday, '+55 years') < date('now')
模型答: [[78.3625730994152]]
gold答: [[72.72727272727273]]

### bird_125  [phase_a_other]  基线 run1=错 run2=错
题面: For loans contracts which are still running where client are in debt, state their district percentage unemployment rate increment from year 1995 to 1996.
形状: 模型 29行×1列 / gold 43行×1列
模型SQL: SELECT 100.0 * (d.A13 - d.A12) / d.A12 AS unemployment_increment FROM loan AS l JOIN account AS a ON l.account_id = a.account_id JOIN district AS d ON a.district_id = d.district_id WHERE l.status = 'D' AND d.A12 IS NOT NULL GROUP BY d.district_id, d.A12, d.A13 ORDER BY d.district_id;
goldSQL: SELECT (d.A13 - d.A12) / d.A12 * 100 FROM loan AS l JOIN account AS a ON l.account_id = a.account_id JOIN district AS d ON a.district_id = d.district_id WHERE l.status = 'D' AND NOT d.A12 IS NULL AND NOT d.A13 IS NULL AND d.A12 > 0
模型答: [[115.0], [16.315789473684216], [9.782608695652177], [38.620689655172406], [20.0], [22.14285714285715], [28.387096774193544], [40.
gold答: [[40.0], [39.259259259259245], [114.99999999999999], [22.499999999999993], [20.0], [11.666666666666679], [44.375], [13.33333333333

### bird_1339  [phase_a_other]  基线 run1=错 run2=错
题面: Calculate Elijah Allen’s average spend per event for events in September and October
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT AVG(expense.cost) FROM expense JOIN member ON expense.link_to_member = member.member_id WHERE member.first_name = 'Elijah' AND member.last_name = 'Allen' AND (SUBSTR(expense.expense_date, 6, 2) = '09' OR SUBSTR(expense.expense_date, 6, 2) = '10')
goldSQL: SELECT SUM(T2.cost)  / COUNT(DISTINCT link_to_budget)
FROM member AS T1 INNER JOIN expense AS T2 ON T1.member_id = T2.link_to_member 
WHERE T1.last_name = 'Allen' AND T1.first_name = 'Elijah' 
AND (SUBSTR(T2.expense_date, 6, 2) = '09' OR SUBSTR(T2.expense_date, 6, 2) = '10')
模型答: [[74.0775]]
gold答: [[84.66]]

### bird_1376  [confident_miss]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后判对
题面: Among all the closed events, which event has the highest spend-to-budget ratio?
形状: 模型 1行×1列 / gold 3行×1列
模型SQL: SELECT e.event_name FROM event AS e INNER JOIN budget AS b ON e.event_id = b.link_to_event WHERE e.status = 'Closed' GROUP BY e.event_id, e.event_name ORDER BY SUM(b.spent) * 1.0 / SUM(b.amount) DESC LIMIT 1
goldSQL: SELECT e.event_name FROM event AS e JOIN budget AS b ON e.event_id = b.link_to_event WHERE e.status = 'Closed' GROUP BY e.event_id, e.event_name HAVING SUM(b.amount) > 0 AND SUM(b.spent) / SUM(b.amount) = ( SELECT MAX(ratio) FROM ( SELECT SUM(b2.spent) * 1.0 / SUM(b2.amount) AS ratio FROM budget AS 
模型答: [["Officers meeting - November"]]
gold答: [["Officers meeting - November"], ["Officers meeting - September"], ["Officers meeting - October"]]

### bird_1472  [phase_a_other]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后仍错
题面: In 2012, who had the least consumption in LAM?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT ym.CustomerID FROM yearmonth AS ym JOIN customers AS c ON ym.CustomerID = c.CustomerID WHERE c.Segment = 'LAM' AND ym.Date BETWEEN '201201' AND '201212' ORDER BY ym.Consumption ASC LIMIT 1;
goldSQL: SELECT T1.CustomerID FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Segment = 'LAM' AND SUBSTR(T2.Date, 1, 4) = '2012' GROUP BY T1.CustomerID ORDER BY SUM(T2.Consumption) ASC LIMIT 1
模型答: [[7653]]
gold答: [[47273]]

### bird_1479  [phase_a_other]  基线 run1=对 run2=错  规则['keep_ties']→规则改写后判对
题面: Which year recorded the most consumption of gas paid in CZK?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT substr(ym.Date, 1, 4) AS Year FROM yearmonth AS ym INNER JOIN customers AS c ON ym.CustomerID = c.CustomerID WHERE c.Currency = 'CZK' GROUP BY substr(ym.Date, 1, 4) ORDER BY SUM(ym.Consumption) DESC LIMIT 1
goldSQL: SELECT SUBSTR(T2.Date, 1, 4) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Currency = 'CZK' GROUP BY SUBSTR(T2.Date, 1, 4) ORDER BY SUM(T2.Consumption) DESC LIMIT 1
模型答: [["2013"]]
gold答: [["2013"]]

### bird_1480  [phase_a_other]  基线 run1=对 run2=对  规则['keep_ties']→规则改写后判对
题面: What was the gas consumption peak month for SME customers in 2013?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT SUBSTR(T1.Date, 5, 2) FROM yearmonth AS T1 INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID WHERE T2.Segment = 'SME' AND T1.Date BETWEEN '201301' AND '201312' GROUP BY SUBSTR(T1.Date, 5, 2) ORDER BY SUM(T1.Consumption) DESC LIMIT 1
goldSQL: SELECT SUBSTR(T2.Date, 5, 2) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE SUBSTR(T2.Date, 1, 4) = '2013' AND T1.Segment = 'SME' GROUP BY SUBSTR(T2.Date, 5, 2) ORDER BY SUM(T2.Consumption) DESC LIMIT 1
模型答: [["04"]]
gold答: [["04"]]

### bird_1482  [phase_a_other]  基线 run1=错 run2=错
题面: Provide the percentage increase in consumption paid in EUR between 2012 and 2013 for SME, LAM, and KAM respectively.
形状: 模型 3行×1列 / gold 1行×3列
模型SQL: SELECT ((SUM(CASE WHEN substr(ym.Date,1,4)='2013' THEN ym.Consumption ELSE 0 END) - SUM(CASE WHEN substr(ym.Date,1,4)='2012' THEN ym.Consumption ELSE 0 END)) * 100.0 / SUM(CASE WHEN substr(ym.Date,1,4)='2012' THEN ym.Consumption ELSE 0 END)) AS PercentageIncrease FROM yearmonth AS ym INNER JOIN cust
goldSQL: SELECT CAST((SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2013%', T2.Consumption, 0)) - SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2012%', T2.Consumption, 0))) AS FLOAT) * 100 / SUM(IIF(T1.Segment = 'SME' AND T2.Date LIKE '2012%', T2.Consumption, 0)), CAST(SUM(IIF(T1.Segment = 'LAM' AND T2.Date LI
模型答: [[734.7140627123255], [539.8291924960649], [553.2053767491262]]
gold答: [[734.7140627123255, 539.8291924960649, 553.2053767491262]]

### bird_1486  [phase_a_other]  基线 run1=错 run2=错
题面: How much more SMEs pay in Czech koruna than in euros? 
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT SUM(CASE WHEN c.Currency = 'CZK' THEN t.Amount * t.Price ELSE 0 END) - SUM(CASE WHEN c.Currency = 'EUR' THEN t.Amount * t.Price ELSE 0 END) FROM transactions_1k AS t JOIN customers AS c ON t.CustomerID = c.CustomerID WHERE c.Segment = 'SME'
goldSQL: SELECT SUM(Currency = 'CZK') - SUM(Currency = 'EUR') FROM customers WHERE Segment = 'SME'
模型答: [[3332351.76]]
gold答: [[23505]]

### bird_1498  [phase_a_other]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后仍错
题面: What is the highest monthly consumption in the year 2012?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT Consumption FROM yearmonth WHERE Date LIKE '2012%' ORDER BY Consumption DESC LIMIT 1
goldSQL: SELECT SUM(Consumption) FROM yearmonth WHERE SUBSTR(Date, 1, 4) = '2012' GROUP BY SUBSTR(Date, 5, 2) ORDER BY SUM(Consumption) DESC LIMIT 1
模型答: [[445279.69]]
gold答: [[51787161.74]]

### bird_1529  [phase_a_other]  基线 run1=错 run2=错
题面: What is the amount spent by customer "38508" at the gas stations? How much had the customer spent in August 2012?
形状: 模型 1行×1列 / gold 1行×2列
模型SQL: SELECT SUM(t.Amount) FROM transactions_1k t WHERE t.CustomerID = 38508 AND t.Date LIKE '2012-08%'
goldSQL: SELECT SUM(Amount * Price) AS total_spent, SUM(CASE WHEN Date LIKE '2012-08%' THEN Amount * Price ELSE 0 END) AS august_2012_spent FROM transactions_1k WHERE CustomerID = 38508
模型答: [[148]]
gold答: [[88612.38, 88612.38]]

### bird_1531  [phase_a_other]  基线 run1=对 run2=错  规则['keep_ties']→规则改写后判对
题面: Who is the top spending customer and how much is the average price per single item purchased by this customer? What currency was being used?
形状: 模型 1行×3列 / gold 1行×3列
模型SQL: SELECT t.CustomerID, SUM(t.Amount * t.Price) / SUM(t.Amount) AS AveragePricePerSingleItem, c.Currency FROM transactions_1k AS t INNER JOIN customers AS c ON t.CustomerID = c.CustomerID GROUP BY t.CustomerID, c.Currency ORDER BY SUM(t.Amount * t.Price) DESC LIMIT 1;
goldSQL: SELECT c.CustomerID, SUM(t.Price * t.Amount) / SUM(t.Amount) AS average_price_per_item, c.Currency FROM transactions_1k AS t JOIN customers AS c ON t.CustomerID = c.CustomerID WHERE t.CustomerID = ( SELECT CustomerID FROM transactions_1k GROUP BY CustomerID ORDER BY SUM(Amount * Price) DESC LIMIT 1 
模型答: [[13665, 5762.49, "CZK"]]
gold答: [[13665, 5762.49, "CZK"]]

### bird_173  [phase_a_other]  基线 run1=错 run2=对
题面: How often does account number 3 request an account statement to be released? What was the aim of debiting 3539 in total?
形状: 模型 1行×2列 / gold 1行×2列
模型SQL: SELECT (SELECT COUNT(*) FROM trans WHERE account_id = 3 AND k_symbol = 'SLUZBY') AS statement_requests, (SELECT DISTINCT k_symbol FROM `order` WHERE amount = 3539 LIMIT 1) AS aim;
goldSQL: SELECT T1.frequency, T2.k_symbol FROM account AS T1 INNER JOIN (SELECT account_id, k_symbol, SUM(amount) AS total_amount FROM "order" GROUP BY account_id, k_symbol) AS T2 ON T1.account_id = T2.account_id WHERE T1.account_id = 3 AND T2.total_amount = 3539
模型答: [[13, "POJISTNE"]]
gold答: [["POPLATEK MESICNE", "POJISTNE"]]

### bird_212  [confident_miss]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后判对
题面: Which element is the least numerous in non-carcinogenic molecules?
形状: 模型 1行×1列 / gold 3行×1列
模型SQL: SELECT atom.element FROM atom INNER JOIN molecule ON atom.molecule_id = molecule.molecule_id WHERE molecule.label = '-' GROUP BY atom.element ORDER BY COUNT(atom.element) ASC LIMIT 1
goldSQL: SELECT `a`.`element`
FROM `atom` AS `a`
JOIN `molecule` AS `m`  ON `a`.`molecule_id` = `m`.`molecule_id`
WHERE `m`.`label` = '-'
GROUP BY `a`.`element`
HAVING COUNT(*) = (
    SELECT MIN(cnt)
    FROM (
        SELECT COUNT(*) AS cnt
        FROM `atom` AS `a2`
        JOIN `molecule` AS `m2` ON `a2
模型答: [["ca"]]
gold答: [["ca"], ["k"], ["pb"]]

### bird_226  [phase_a_other]  基线 run1=对 run2=错
题面: What is the percentage of double bonds in the molecule TR008? Please provide your answer as a percentage with five decimal places.
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT ROUND(100.0 * SUM(bond_type = '=') / COUNT(bond_id), 5) AS percentage FROM bond WHERE molecule_id = 'TR008';
goldSQL: SELECT ROUND(CAST(COUNT(CASE WHEN T.bond_type = '=' THEN T.bond_id ELSE NULL END) AS REAL) * 100 / COUNT(T.bond_id),5) FROM bond AS T WHERE T.molecule_id = 'TR008'
模型答: [[3.84615]]
gold答: [[3.84615]]

### bird_227  [phase_a_other]  基线 run1=对 run2=错
题面: What is the percentage of molecules that are carcinogenic? Please provide your answer as a percentage with three decimal places.
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT ROUND(100.0 * SUM(label = '+') / COUNT(molecule_id), 3) FROM molecule;
goldSQL: SELECT ROUND(CAST(COUNT(CASE WHEN T.label = '+' THEN T.molecule_id ELSE NULL END) AS REAL) * 100 / COUNT(T.molecule_id),3) FROM molecule t
模型答: [[44.315]]
gold答: [[44.315]]

### bird_228  [phase_a_other]  基线 run1=错 run2=对  规则['printf_to_round']→规则改写后判对
题面: How much of the hydrogen in molecule TR206 is accounted for? Please provide your answer as a percentage with four decimal places.
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT printf('%.4f', 100.0 * SUM(element = 'h') / COUNT(atom_id)) AS percent FROM atom WHERE molecule_id = 'TR206'
goldSQL: SELECT ROUND(CAST(COUNT(CASE WHEN T.element = 'h' THEN T.atom_id ELSE NULL END) AS REAL) * 100 / COUNT(T.atom_id),4) FROM atom AS T WHERE T.molecule_id = 'TR206'
模型答: [["45.4545"]]
gold答: [[45.4545]]

### bird_24  [phase_a_other]  基线 run1=错 run2=错
题面: Give the names of the schools with the percent eligible for free meals in K-12 is more than 0.1 and test takers whose test score is greater than or equal to 1500?
形状: 模型 1084行×1列 / gold 1142行×1列
模型SQL: SELECT DISTINCT T3.[School] FROM frpm AS T1 INNER JOIN satscores AS T2 ON T2.cds = T1.CDSCode INNER JOIN schools AS T3 ON T3.CDSCode = T1.CDSCode WHERE 1.0 * T1.[Free Meal Count (K-12)] / T1.[Enrollment (K-12)] > 0.1 AND T2.NumGE1500 > 0
goldSQL: SELECT T2."School Name"
FROM satscores AS T1 INNER JOIN frpm AS T2 ON T1.cds = T2.CDSCode 
WHERE CAST(T2."Free Meal Count (K-12)" AS REAL) / T2."Enrollment (K-12)" > 0.1 AND T1.NumGE1500 > 0 AND rtype = 'S'
模型答: [["FAME Public Charter"], ["Envision Academy for Arts & Technology"], ["Alameda Science and Technology Institute"], ["Alameda High
gold答: [["FAME Public Charter"], ["Envision Academy for Arts & Technology"], ["Alameda Science and Technology Institute"], ["Alameda High

### bird_255  [phase_a_other]  基线 run1=错 run2=错  规则['printf_to_round']→规则改写后判对
题面: What percentage of all single bonds occur in carcinogenic molecules?  Please provide your answer as a percentage with five decimal places.
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT printf('%.5f', 100.0 * SUM(CASE WHEN m.label = '+' THEN 1 ELSE 0 END) / COUNT(*)) AS percentage FROM bond AS b JOIN molecule AS m ON b.molecule_id = m.molecule_id WHERE b.bond_type = '-';
goldSQL: SELECT ROUND(CAST(COUNT(CASE WHEN T2.label = '+' THEN T1.bond_id ELSE NULL END) AS REAL) * 100 / COUNT(T1.bond_id),5) 
FROM bond AS T1  JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id WHERE T1.bond_type = '-'
模型答: [["39.75203"]]
gold答: [[39.75203]]

### bird_26  [phase_a_other]  基线 run1=错 run2=错
题面: State the names and full communication address of high schools in Monterey which has more than 800 free or reduced price meals for ages 5-17?
形状: 模型 6行×5列 / gold 6行×5列
模型SQL: SELECT s.School AS Name, s.Street, s.City, s.State, CASE WHEN NOT s.Zip IS NULL AND s.Zip <> '' THEN ' ' || s.Zip ELSE '' END FROM schools AS s INNER JOIN frpm AS f ON s.CDSCode = f.CDSCode WHERE f."County Name" = 'Monterey' AND f."School Type" = 'High Schools (Public)' AND f."FRPM Count (Ages 5-17)
goldSQL: SELECT T1."School Name", T2.Street, T2.City, T2.State, T2.Zip
FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode 
WHERE T2.County = 'Monterey' AND T1."FRPM Count (Ages 5-17)" > 800 AND T1."School Type" = 'High Schools (Public)' AND T2.School is not NULL
模型答: [["Alisal High", "777 Williams Road", "Salinas", "CA", " 93905-1907"], ["Everett Alvarez High", "1900 Independence Boulevard", "Sa
gold答: [["Alisal High", "777 Williams Road", "Salinas", "CA", "93905-1907"], ["Everett Alvarez High", "1900 Independence Boulevard", "Sal

### bird_263  [phase_a_other]  基线 run1=对 run2=对
题面: What is the composition of element chlorine in percentage among the molecules that contain at least one single bond?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT 100.0 * SUM(a.element = 'cl') / COUNT(a.atom_id) AS percent FROM atom AS a WHERE EXISTS (SELECT 1 FROM bond AS b WHERE b.molecule_id = a.molecule_id AND b.bond_type = '-')
goldSQL: SELECT CAST(COUNT(CASE WHEN T.element = 'cl' THEN T.atom_id ELSE NULL END) AS REAL) * 100 / COUNT(T.atom_id) FROM atom AS T WHERE molecule_id IN (SELECT DISTINCT molecule.molecule_id FROM molecule JOIN bond ON molecule.molecule_id = bond.molecule_id AND bond.bond_type = '-')
模型答: [[3.4823684499615513]]
gold答: [[3.4823684499615513]]

### bird_273  [phase_a_other]  基线 run1=错 run2=错
题面: What is the percentage of element chlorine in carcinogenic molecules?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT CAST(SUM(atom.element = 'cl') AS REAL) / COUNT(atom.element) AS percentage FROM atom JOIN molecule ON atom.molecule_id = molecule.molecule_id WHERE molecule.label = '+';
goldSQL: SELECT CAST(COUNT( CASE WHEN T1.element = 'cl' THEN T1.element ELSE NULL END) AS REAL) * 100 / COUNT(T1.element) FROM atom AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id WHERE T2.label = '+'
模型答: [[0.0314192849404117]]
gold答: [[3.1419284940411703]]

### bird_32  [phase_a_other]  基线 run1=错 run2=对
题面: What is the eligible free or reduced price meal rate for the top 5 schools in K-12 with the highest free or reduced price meal count of the schools with the ownership code 66?
形状: 模型 3行×1列 / gold 5行×1列
模型SQL: SELECT 1.0 * f."FRPM Count (K-12)" / f."Enrollment (K-12)" AS eligible_free_or_reduced_price_meal_rate FROM frpm AS f INNER JOIN schools AS s ON f.CDSCode = s.CDSCode WHERE s.SOC = '66' AND s.GSserved = 'K-12' ORDER BY f."FRPM Count (K-12)" DESC LIMIT 5;
goldSQL: SELECT CAST(T1."FRPM Count (K-12)" AS REAL) / T1."Enrollment (K-12)" FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.SOC = 66 ORDER BY T1."FRPM Count (K-12)" DESC LIMIT 5
模型答: [[0.5025210084033613], [0.6976744186046512], [0.76]]
gold答: [[0.9179476526796843], [0.9993290841999329], [0.8964987714987716], [0.8958203368683718], [0.9141803553469662]]

### bird_349  [confident_miss]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后判对
题面: Name the card with the most ruling information and its artist. Also state if the card is a promotional printing.
形状: 模型 1行×3列 / gold 2行×3列
模型SQL: SELECT cards.name, cards.artist, cards.isPromo FROM cards INNER JOIN rulings ON cards.uuid = rulings.uuid GROUP BY cards.uuid, cards.name, cards.artist, cards.isPromo ORDER BY COUNT(rulings.uuid) DESC LIMIT 1
goldSQL: SELECT DISTINCT c.name, c.artist, c.isPromo FROM cards c INNER JOIN (SELECT uuid FROM rulings GROUP BY uuid HAVING COUNT(id) = ( SELECT MAX(ruling_count) FROM ( SELECT COUNT(id) as ruling_count FROM rulings GROUP BY uuid ) ) ) AS max_rulings ON c.uuid = max_rulings.uuid;
模型答: [["Teferi's Protection", "Chase Stone", 0]]
gold答: [["Teferi's Protection", "Chase Stone", 0], ["Teferi's Protection", "Chase Stone", 1]]

### bird_352  [phase_a_other]  基线 run1=错 run2=错
题面: Calculate the percentage of the cards availabe in Chinese Simplified.
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT CAST(COUNT(CASE WHEN language = 'Chinese Simplified' THEN id ELSE NULL END) AS REAL) * 100 / COUNT(id) FROM set_translations
goldSQL: SELECT CAST(COUNT(DISTINCT CASE WHEN T2.language = 'Chinese Simplified' THEN T1.id ELSE NULL END) AS REAL) * 100 / COUNT(DISTINCT T1.id) FROM cards AS T1 LEFT JOIN foreign_data AS T2 ON T1.uuid = T2.uuid
模型答: [[10.0]]
gold答: [[35.384182182957304]]

### bird_36  [phase_a_other]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后仍错
题面: Under whose administration is the school with the highest number of students scoring 1500 or more on the SAT? Indicate their full names.
形状: 模型 1行×2列 / gold 1行×6列
模型SQL: SELECT sch.AdmFName1, sch.AdmLName1 FROM schools sch JOIN satscores sat ON sat.cds = sch.CDSCode ORDER BY sat.NumGE1500 DESC LIMIT 1
goldSQL: SELECT s.AdmFName1,
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

### bird_37  [confident_miss]  基线 run1=错 run2=错
题面: What is the complete address of the school with the lowest excellence rate? Indicate the Street, City, State, and Zip.
形状: 模型 1行×4列 / gold 17行×4列
模型SQL: SELECT s.Street, s.City, s.State, s.Zip FROM schools AS s INNER JOIN satscores AS t ON t.cds = s.CDSCode WHERE t.NumTstTakr > 0 AND t.NumGE1500 IS NOT NULL ORDER BY CAST(t.NumGE1500 AS REAL) / t.NumTstTakr ASC, s.CDSCode ASC LIMIT 1
goldSQL: SELECT s.Street, s.City, s.State, s.Zip 
FROM schools s JOIN satscores sat ON s.CDSCode = sat.cds 
WHERE sat.NumTstTakr > 0 AND sat.NumGE1500 IS NOT NULL AND sat.NumTstTakr IS NOT NULL  AND rtype = 'S'
AND CAST(sat.NumGE1500 AS FLOAT) / CAST(sat.NumTstTakr AS FLOAT) =
 (SELECT MIN(CAST(NumGE1500 AS 
模型答: [["2607 Myrtle Street", "Oakland", "CA", "94607-3415"]]
gold答: [["2607 Myrtle Street", "Oakland", "CA", "94607-3415"], ["4521 Webster Street", "Oakland", "CA", "94609-2140"], ["2465 Dolan Way",

### bird_383  [phase_a_other]  基线 run1=对 run2=对
题面: How many of the banned cards are white border?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT COUNT(DISTINCT cards.uuid) FROM cards JOIN legalities ON cards.uuid = legalities.uuid WHERE legalities.status = 'Banned' AND cards.borderColor = 'white'
goldSQL: SELECT COUNT(DISTINCT T1.id) FROM cards AS T1 INNER JOIN legalities AS T2 ON T1.uuid = T2.uuid WHERE T2.status = 'Banned' AND T1.borderColor = 'white'
模型答: [[89]]
gold答: [[89]]

### bird_407  [phase_a_other]  基线 run1=错 run2=错
题面: Lists all types of cards in German.
形状: 模型 492行×1列 / gold 1693行×2列
模型SQL: SELECT DISTINCT T1.type FROM foreign_data AS T1 INNER JOIN cards AS T2 ON T1.uuid = T2.uuid WHERE T1.language = 'German' AND T2.subtypes IS NOT NULL AND T2.supertypes IS NOT NULL ORDER BY T1.type
goldSQL: SELECT T1.subtypes, T1.supertypes FROM cards AS T1 INNER JOIN foreign_data AS T2 ON T1.uuid = T2.uuid WHERE T2.language = 'German' AND T1.subtypes IS NOT NULL AND T1.supertypes IS NOT NULL
模型答: [[""], ["Artefaktkreatur — Golem, Legende"], ["Artefaktkreatur — Zauberer, Legende"], ["Beschwörung einer Legende"], ["Kreatur — A
gold答: [["Human,Rebel", "Legendary"], ["Angel", "Legendary"], ["Merfolk,Wizard", "Legendary"], ["Vampire,Noble", "Legendary"], ["Avatar,M

### bird_416  [phase_a_other]  基线 run1=错 run2=错
题面: What percentage of cards without power are in French?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT CAST(COUNT(CASE WHEN f.language = 'French' THEN 1 END) AS REAL) * 100.0 / COUNT(*) FROM cards AS c LEFT JOIN foreign_data AS f ON f.uuid = c.uuid WHERE c.power IS NULL OR c.power = '*'
goldSQL: SELECT CAST(COUNT(DISTINCT CASE WHEN T2.language = 'French' THEN T1.id ELSE NULL END) AS REAL) * 100 / COUNT(DISTINCT T1.id) FROM cards AS T1 LEFT JOIN foreign_data AS T2 ON T1.uuid = T2.uuid WHERE T1.power IS NULL OR T1.power = '*'
模型答: [[11.58288545450303]]
gold答: [[47.95671915756932]]

### bird_465  [phase_a_other]  基线 run1=错 run2=错
题面: Which sets of cards with "Ancestor's Chosen" in it have a Korean version?
形状: 模型 0行 / gold 2行×1列
模型SQL: SELECT DISTINCT sets.name FROM cards INNER JOIN foreign_data ON foreign_data.uuid = cards.uuid INNER JOIN sets ON cards.setCode = sets.code WHERE cards.name = 'Ancestor''s Chosen' AND foreign_data.language = 'Korean';
goldSQL: SELECT DISTINCT T3.name FROM cards AS T1 INNER JOIN set_translations AS T2 ON T2.setCode = T1.setCode INNER JOIN sets AS T3 ON T3.code = T1.setCode WHERE T1.name = 'Ancestor''s Chosen' AND T2.language = 'Korean'
模型答: []
gold答: [["Tenth Edition"], ["Judgment"]]

### bird_48  [phase_a_other]  基线 run1=错 run2=错
题面: What is the ratio of merged Unified School District schools in Orange County to merged Elementary School District schools?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT 1.0 * (SELECT COUNT(*) FROM schools WHERE County = 'Orange' AND DOC = '54' AND StatusType = 'Merged') / NULLIF((SELECT COUNT(*) FROM schools WHERE DOC = '52' AND StatusType = 'Merged'), 0) AS ratio
goldSQL: SELECT CAST((
SELECT COUNT(*) FROM schools 
WHERE County = 'Orange' AND DOC = '54' AND StatusType = 'Merged' AND school is not null) AS REAL) 
/ (SELECT COUNT(*) FROM schools WHERE DOC = '52' AND StatusType = 'Merged' AND school is not null) AS ratio;
模型答: [[0.008403361344537815]]
gold答: [[0.010958904109589041]]

### bird_50  [phase_a_other]  基线 run1=错 run2=错
题面: What is the postal street address for the school with the 7th highest Math average? Indicate the school's name.
形状: 模型 1行×2列 / gold 1行×2列
模型SQL: SELECT COALESCE(ss.sname, sh.School) AS school_name, sh.MailStreet AS postal_street_address FROM satscores AS ss INNER JOIN schools AS sh ON ss.cds = sh.CDSCode WHERE ss.AvgScrMath IS NOT NULL ORDER BY ss.AvgScrMath DESC, ss.cds ASC LIMIT 1 OFFSET 6
goldSQL: SELECT s.`MailStreet`   AS postal_street_address,
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

### bird_587  [phase_a_other]  基线 run1=错 run2=错
题面: For each post tagged 'humor', list the title, the comment, and the overall average view count across all posts tagged 'humor'.
形状: 模型 19行×3列 / gold 9行×3列
模型SQL: SELECT p.Title, c.Text AS comment, (SELECT AVG(ViewCount) FROM posts WHERE Tags LIKE '%<humor>%') AS average_view_count FROM posts AS p LEFT JOIN comments AS c ON c.PostId = p.Id WHERE p.Tags LIKE '%<humor>%';
goldSQL: SELECT p.Title, c.Text AS Comment, ( 
SELECT AVG(ViewCount) 
FROM posts WHERE Tags LIKE '<humor>' ) AS AverageViewCount 
FROM posts AS p JOIN comments AS c ON p.Id = c.PostId WHERE p.Tags = '<humor>'
模型答: [["So how many staticians *does* it take to screw in a lightbulb?", "@Jason Punyon in particular gets a humorless downvote for rem
gold答: [["So how many staticians *does* it take to screw in a lightbulb?", "Probably better asked on meta.  People feel like they have to

### bird_604  [phase_a_other]  基线 run1=错 run2=错
题面: What is the average of the up votes and the average user age for users creating more than 10 posts?
形状: 模型 1行×2列 / gold 1行×2列
模型SQL: SELECT CAST(SUM(T1.UpVotes) AS REAL) / COUNT(T1.Id), CAST(SUM(T1.Age) AS REAL) / COUNT(T1.Id) FROM users AS T1 INNER JOIN ( SELECT T2.OwnerUserId AS UserId FROM posts AS T2 GROUP BY T2.OwnerUserId HAVING COUNT(T2.OwnerUserId) > 10 ) AS T3 ON T1.Id = T3.UserId
goldSQL: SELECT AVG(T1.UpVotes), AVG(T1.Age) FROM users AS T1 INNER JOIN ( SELECT OwnerUserId, COUNT(*) AS post_count FROM posts GROUP BY OwnerUserId HAVING post_count > 10) AS T2 ON T1.Id = T2.OwnerUserId
模型答: [[182.2832618025751, 9.127896995708154]]
gold答: [[182.2832618025751, 34.083333333333336]]

### bird_637  [phase_a_other]  基线 run1=错 run2=错
题面: State all the tags used by Mark Meckes in his posts that doesn't have comments.
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: WITH RECURSIVE tag_split(post_id, tag, rest) AS (SELECT p.Id, substr(p.Tags, 2, instr(p.Tags, '>') - 2) AS tag, substr(p.Tags, instr(p.Tags, '>') + 1) AS rest FROM posts AS p INNER JOIN users AS u ON p.OwnerUserId = u.Id WHERE u.DisplayName = 'Mark Meckes' AND p.CommentCount = 0 AND p.Tags IS NOT NU
goldSQL: SELECT DISTINCT p.`Tags`
FROM `posts` p
JOIN `users` u ON u.`Id` = p.`OwnerUserId`
WHERE u.`DisplayName` = 'Mark Meckes'
  AND p.`CommentCount` = 0
  AND p.`Tags` IS NOT NULL;
模型答: [["books"]]
gold答: [["<books>"]]

### bird_640  [phase_a_other]  基线 run1=错 run2=对
题面: Calculate the difference in view count from post posted by Mornington and view count from posts posted by Amos.
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT SUM(CASE WHEN OwnerDisplayName = 'Mornington' THEN ViewCount ELSE 0 END) - SUM(CASE WHEN OwnerDisplayName = 'Amos' THEN ViewCount ELSE 0 END) FROM posts;
goldSQL: SELECT SUM(CASE WHEN u.DisplayName = 'Mornington' THEN p.ViewCount ELSE 0 END) - SUM(CASE WHEN u.DisplayName = 'Amos' THEN p.ViewCount ELSE 0 END) FROM posts p JOIN users u ON p.OwnerUserId = u.Id WHERE u.DisplayName IN ('Mornington', 'Amos') AND p.ViewCount IS NOT NULL;
模型答: [[0]]
gold答: [[-497]]

### bird_671  [confident_miss]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后判对
题面: What is the display name of the user who acquired the first Autobiographer badge?
形状: 模型 1行×1列 / gold 12行×1列
模型SQL: SELECT u.DisplayName FROM badges b JOIN users u ON b.UserId = u.Id WHERE b.Name = 'Autobiographer' ORDER BY b.Date ASC LIMIT 1
goldSQL: SELECT DISTINCT u.DisplayName FROM users AS u JOIN badges AS b ON u.Id = b.UserId WHERE b.Name = 'Autobiographer' AND b.Date = ( SELECT MIN(Date) FROM badges WHERE Name = 'Autobiographer')
模型答: [["Geoff Dalgas"]]
gold答: [["Geoff Dalgas"], ["Jarrod Dixon"], ["Vince"], ["csgillespie"], ["Pierre"], ["wahalulu"], ["Jin"], ["Sharpie"], ["grokus"], ["Noa

### bird_736  [confident_miss]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后判对
题面: Who is the dumbest superhero?
形状: 模型 1行×1列 / gold 3行×1列
模型SQL: SELECT T2.superhero_name FROM hero_attribute AS T1 INNER JOIN superhero AS T2 ON T1.hero_id = T2.id INNER JOIN attribute AS T3 ON T1.attribute_id = T3.id WHERE T3.attribute_name = 'Intelligence' ORDER BY T1.attribute_value ASC LIMIT 1
goldSQL: SELECT s.superhero_name FROM superhero AS s JOIN hero_attribute AS ha ON s.id = ha.hero_id JOIN attribute AS a ON ha.attribute_id = a.id WHERE a.attribute_name = 'Intelligence' AND ha.attribute_value = ( SELECT MIN(attribute_value) FROM hero_attribute WHERE attribute_id = ( SELECT id FROM attribute 
模型答: [["Ammo"]]
gold答: [["Ammo"], ["Ando Masahashi"], ["Jack-Jack"]]

### bird_744  [confident_miss]  基线 run1=错 run2=错
题面: Between DC and Marvel Comics, which publisher has published more superheroes? Find the difference in the number of superheroes they have published.
形状: 模型 1行×1列 / gold 1行×2列
模型SQL: SELECT SUM(p.publisher_name = 'Marvel Comics') - SUM(p.publisher_name = 'DC Comics') AS difference FROM superhero AS s JOIN publisher AS p ON s.publisher_id = p.id WHERE p.publisher_name IN ('Marvel Comics', 'DC Comics')
goldSQL: SELECT CASE WHEN marvel_cnt > dc_cnt THEN 'Marvel Comics' ELSE 'DC Comics' END AS publisher_with_more_superheroes,
       marvel_cnt - dc_cnt AS difference
FROM (
    SELECT SUM(CASE WHEN p.`publisher_name`='Marvel Comics' THEN 1 END) AS marvel_cnt,
           SUM(CASE WHEN p.`publisher_name`='DC Co
模型答: [[163]]
gold答: [["Marvel Comics", 163]]

### bird_750  [phase_a_other]  基线 run1=错 run2=错
题面: What is the average weight of all female superheroes?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT AVG(T1.weight_kg) FROM superhero AS T1 INNER JOIN gender AS T2 ON T1.gender_id = T2.id WHERE T2.gender = 'Female'
goldSQL: SELECT AVG(weight_kg) FROM superhero s JOIN gender g ON s.gender_id = g.id WHERE g.gender = 'Female' AND weight_kg > 0;
模型答: [[60.77956989247312]]
gold答: [[78.50694444444444]]

### bird_791  [phase_a_other]  基线 run1=错 run2=对
题面: Calculate the average height for all superhero.
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT AVG(height_cm) FROM superhero;
goldSQL: SELECT AVG(height_cm) FROM superhero WHERE height_cm > 0;
模型答: [[267.7514450867052]]
gold答: [[345.03538175046555]]

### bird_794  [confident_miss]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后判对
题面: Which hero was the fastest?
形状: 模型 1行×1列 / gold 40行×1列
模型SQL: SELECT s.superhero_name FROM superhero AS s JOIN hero_attribute AS ha ON ha.hero_id = s.id JOIN attribute AS a ON a.id = ha.attribute_id WHERE a.attribute_name = 'Speed' ORDER BY ha.attribute_value DESC LIMIT 1
goldSQL: SELECT s.superhero_name FROM superhero AS s JOIN hero_attribute AS ha ON s.id = ha.hero_id JOIN attribute AS a ON ha.attribute_id = a.id WHERE a.attribute_name = 'Speed' AND ha.attribute_value = ( SELECT MAX(ha2.attribute_value) FROM hero_attribute AS ha2 JOIN attribute AS a2 ON ha2.attribute_id = a
模型答: [["Air-Walker"]]
gold答: [["Air-Walker"], ["Angela"], ["Ardina"], ["Aurora"], ["Ben 10"], ["Beyonder"], ["Binary"], ["Bizarro"], ["Black Bolt"], ["Black Fl

### bird_829  [confident_miss]  基线 run1=错 run2=错
题面: Which publisher created more superheroes: DC or Marvel Comics? Find the difference in the number of superheroes.
形状: 模型 1行×1列 / gold 1行×2列
模型SQL: SELECT SUM(p.publisher_name = 'DC Comics') - SUM(p.publisher_name = 'Marvel Comics') AS difference FROM superhero AS s JOIN publisher AS p ON s.publisher_id = p.id;
goldSQL: SELECT CASE WHEN marvel_cnt > dc_cnt THEN 'Marvel Comics' ELSE 'DC Comics' END AS publisher_with_more_superheroes,
        dc_cnt - marvel_cnt AS difference
FROM (
    SELECT SUM(CASE WHEN p.`publisher_name`='Marvel Comics' THEN 1 END) AS marvel_cnt,
           SUM(CASE WHEN p.`publisher_name`='DC C
模型答: [[-163]]
gold答: [["Marvel Comics", -163]]

### bird_85  [phase_a_other]  基线 run1=错 run2=错
题面: What is the Percent (%) Eligible Free (K-12) in the school administered by an administrator whose first name is Alusine. List the district code of the school.
形状: 模型 1行×2列 / gold 1行×2列
模型SQL: SELECT f."Percent (%) Eligible Free (K-12)", f."District Code" FROM schools AS s JOIN frpm AS f ON s.CDSCode = f.CDSCode WHERE s."AdmFName1" = 'Alusine'
goldSQL: SELECT T1."Free Meal Count (K-12)" * 100 / T1."Enrollment (K-12)", T1."District Code" FROM frpm AS T1 INNER JOIN schools AS T2 ON T1.CDSCode = T2.CDSCode WHERE T2.AdmFName1 = 'Alusine'
模型答: [[0.701511335012594, 64857]]
gold答: [[70.15113350125945, 64857]]

### bird_881  [phase_a_other]  基线 run1=对 run2=对
题面: For the drivers who took part in the race in 1983/7/16, what's their race completion rate?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT CAST(COUNT(CASE WHEN status.status = 'Finished' OR status.status LIKE '+% Lap%' THEN results.driverId END) AS REAL) * 100.0 / COUNT(results.driverId) AS percentage FROM results INNER JOIN races ON results.raceId = races.raceId INNER JOIN status ON results.statusId = status.statusId WHERE race
goldSQL: SELECT 100.0 * SUM(CASE
                     WHEN s.`status` = 'Finished'
                          OR s.`status` LIKE '+% Lap%'
                   THEN 1 ELSE 0 END) / COUNT(*) AS completion_rate
FROM `races` r
JOIN `results` res ON res.`raceId` = r.`raceId`
JOIN `status`  s   ON s.`statusId` = res
模型答: [[58.62068965517241]]
gold答: [[58.62068965517241]]

### bird_894  [phase_a_other]  基线 run1=错 run2=错  规则['keep_ties']→规则改写后仍错
题面: What is the best lap time recorded? List the recorded lap time, driver, and race.
形状: 模型 1行×4列 / gold 1行×4列
模型SQL: SELECT lt.time, d.forename, d.surname, r.name FROM lapTimes lt JOIN drivers d ON lt.driverId = d.driverId JOIN races r ON lt.raceId = r.raceId ORDER BY lt.milliseconds ASC LIMIT 1
goldSQL: SELECT T2.milliseconds, T1.forename, T1.surname, T3.name FROM drivers AS T1 INNER JOIN lapTimes AS T2 ON T1.driverId = T2.driverId INNER JOIN races AS T3 ON T2.raceId = T3.raceId ORDER BY T2.milliseconds ASC LIMIT 1
模型答: [["1:07.411", "Lewis", "Hamilton", "Austrian Grand Prix"]]
gold答: [[67411, "Lewis", "Hamilton", "Austrian Grand Prix"]]

### bird_928  [phase_a_other]  基线 run1=对 run2=对
题面: Which driver ranked the first in the Canadian Grand Prix in 2007? Please give his forename, surname, and reference name.
形状: 模型 1行×3列 / gold 1行×3列
模型SQL: SELECT d.forename, d.surname, d.driverRef FROM results AS r JOIN races AS ra ON r.raceId = ra.raceId JOIN drivers AS d ON r.driverId = d.driverId WHERE ra.name = 'Canadian Grand Prix' AND ra.year = 2007 AND r.position = 1
goldSQL: SELECT d.forename, d.surname, d.driverRef FROM drivers AS d JOIN results AS r ON d.driverId = r.driverId JOIN races AS ra ON r.raceId = ra.raceId WHERE ra.name = 'Canadian Grand Prix' AND ra.year = 2007 AND r.position = 1
模型答: [["Lewis", "Hamilton", "hamilton"]]
gold答: [["Lewis", "Hamilton", "hamilton"]]

### bird_931  [phase_a_other]  基线 run1=错 run2=对
题面: What was the fastest lap speed among all drivers in the 2009 Spanish Grand Prix?
形状: 模型 1行×1列 / gold 1行×1列
模型SQL: SELECT MAX(CAST(r.fastestLapSpeed AS REAL)) FROM results AS r INNER JOIN races AS ra ON r.raceId = ra.raceId WHERE ra.year = 2009 AND ra.name = 'Spanish Grand Prix'
goldSQL: SELECT T2.fastestLapSpeed FROM races AS T1 INNER JOIN results AS T2 ON T2.raceId = T1.raceId WHERE T1.name = 'Spanish Grand Prix' AND T1.year = 2009 AND T2.fastestLapSpeed IS NOT NULL ORDER BY T2.fastestLapSpeed DESC LIMIT 1
模型答: [[202.484]]
gold答: [["202.484"]]
