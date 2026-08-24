# 并列约定：人工判读用对照表（2026-08-24）

问题：这两组题在题面上，人能不能看出该返回一个还是全部并列？
第一组 gold 用 `= (SELECT MAX…)`（返回全部并列），第二组 gold 用 `LIMIT 1`（只返回一行）。
两组都来自 `e3_c_rules_reasoning_corrected_run1` 的 singular-superlative 类。

---

## 第一组：gold 保留全部并列（MAX-subquery），14 道

### bird_1122  [MAX-subquery]  答对

**题面**：State the name of the most strongest player.

**gold 返回 1 行**：`[['Lionel Messi']]`

**gold SQL**：`SELECT DISTINCT t1.player_name FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_api_id = t2.player_api_id WHERE t2.overall_rating = (SELECT MAX(overall_rating) FROM Player_Attributes)`

**模型 SQL**：`SELECT P.player_name FROM Player_Attributes AS PA INNER JOIN Player AS P ON PA.player_api_id = P.player_api_id ORDER BY PA.overall_rating DESC LIMIT 1;`
### bird_1136  [MAX-subquery]  答对

**题面**：How many players had the highest potential score for crossing that preferred to use their left foots while attacking?

**gold 返回 1 行**：`[[2]]`

**gold SQL**：`SELECT COUNT(DISTINCT t1.player_api_id) FROM Player_Attributes AS t1 WHERE t1.preferred_foot = 'left' AND t1.crossing = ( SELECT MAX(crossing) FROM Player_Attributes)`

**模型 SQL**：`SELECT COUNT(DISTINCT player_api_id) FROM Player_Attributes WHERE preferred_foot = 'left' AND crossing = (SELECT MAX(crossing) FROM Player_Attributes);`
### bird_1144  [MAX-subquery]  答对

**题面**：Please state the finishing rates and curve scores from all records for the players with the highest weight.

**gold 返回 38 行**：`[[13, 13], [13, 13], [13, 13], [13, 13], [12, 12], [12, 12], [12, 12], [12, 12], [12, 12], [21, 12], [21, 12], [21, 12], [21, 12], [21, 12], [12, 15], [12, 15], [25, 25], [25, 25], [25, 25], [25, 25], [25, 25], [25, 25], [25, 25], [11, 14], [11, 14], [11, 14], [11, 14], [11, 14], [11, 14], [11, 14],`

**gold SQL**：`SELECT finishing, curve FROM Player_Attributes WHERE player_api_id IN (SELECT player_api_id FROM Player WHERE weight = (SELECT MAX(weight) from Player))`

**模型 SQL**：`SELECT PA.finishing, PA.curve FROM Player_Attributes AS PA INNER JOIN Player AS P ON PA.player_api_id = P.player_api_id WHERE P.weight = (SELECT MAX(weight) FROM Player)`
### bird_1147  [MAX-subquery]  答对

**题面**：Please name one player whose overall rating is the greatest.

**gold 返回 1 行**：`[['Lionel Messi']]`

**gold SQL**：`SELECT DISTINCT t1.player_name FROM Player AS t1 INNER JOIN Player_Attributes AS t2 ON t1.player_api_id = t2.player_api_id WHERE t2.overall_rating = ( SELECT MAX(overall_rating) FROM Player_Attributes)`

**模型 SQL**：`SELECT T2.player_name FROM Player_Attributes AS T1 INNER JOIN Player AS T2 ON T1.player_api_id = T2.player_api_id WHERE T1.overall_rating IS NOT NULL ORDER BY T1.overall_rating DESC LIMIT 1;`
### bird_1166  [MAX-subquery]  答对

**题面**：What are the symptoms observed by the youngest patient to ever did a medical examination? Identify the patient diagnosis.

**gold 返回 1 行**：`[[None, 'SJS']]`

**gold SQL**：`SELECT DISTINCT e.Symptoms, p.Diagnosis FROM Patient AS p INNER JOIN Examination AS e ON p.ID = e.ID WHERE p.Birthday = ( SELECT MAX(p2.Birthday) FROM Patient AS p2 INNER JOIN Examination AS e2 ON p2.ID = e2.ID ) AND NOT e.Symptoms IS NULL UNION SELECT NULL AS Symptoms, p.Diagnosis FROM Patient AS p WHERE p.ID = (SELECT p2.ID FROM Patient AS p2 INNER JOIN Examination AS e2 ON p2.ID = e2.ID WHERE p`

**模型 SQL**：`SELECT E.Symptoms, P.Diagnosis FROM Examination AS E INNER JOIN Patient AS P ON E.ID = P.ID ORDER BY P.Birthday DESC LIMIT 1`
### bird_244  [MAX-subquery]  答对

**题面**：Is the molecule with the most double bonds carcinogenic? Show its label.

**gold 返回 2 行**：`[['+'], ['+']]`

**gold SQL**：`with sub as ( SELECT T.molecule_id, COUNT(T.bond_type) as cnt FROM bond AS T WHERE T.bond_type = '=' GROUP BY T.molecule_id ) SELECT T1.label FROM molecule AS T1 INNER JOIN sub AS T2 ON T1.molecule_id = T2.molecule_id WHERE T2.cnt = (select max(cnt) from sub)`

**模型 SQL**：`SELECT m.label FROM molecule AS m JOIN bond AS b ON m.molecule_id = b.molecule_id WHERE b.bond_type = '=' GROUP BY m.molecule_id, m.label ORDER BY COUNT(*) DESC LIMIT 1`
### bird_786  [MAX-subquery]  答对

**题面**：How many heroes have the highest attribute value in strength?

**gold 返回 1 行**：`[[63]]`

**gold SQL**：`SELECT COUNT(DISTINCT ha.`hero_id`) FROM `hero_attribute` AS ha JOIN `attribute` AS a ON ha.`attribute_id` = a.`id` WHERE a.`attribute_name` = 'Strength' AND ha.`attribute_value` = ( SELECT MAX(ha2.`attribute_value`) FROM `hero_attribute` ha2 JOIN `attribute` a2 ON ha2.`attribute_id` = a2.`id` WHERE a2.`attribute_name` = 'Strength' );`

**模型 SQL**：`SELECT COUNT(DISTINCT ha.hero_id) FROM hero_attribute AS ha JOIN attribute AS a ON ha.attribute_id = a.id WHERE a.attribute_name = 'Strength' AND ha.attribute_value = (SELECT MAX(ha2.attribute_value) FROM hero_attribute AS ha2 JOIN attribute AS a2 ON ha2.attribute_id = a2.id WHERE a2.attribute_name = 'Strength')`
### bird_1028  [MAX-subquery]  答错

**题面**：In Scotland Premier League, which away team won the most during the 2010 season?

**gold 返回 2 行**：`[['Rangers'], ['Celtic']]`

**gold SQL**：`SELECT DISTINCT t.team_long_name FROM Team t JOIN Match m ON t.team_api_id = m.away_team_api_id JOIN League l ON m.league_id = l.id WHERE l.name = 'Scotland Premier League' AND m.season = '2009/2010' AND m.away_team_goal > m.home_team_goal GROUP BY t.team_api_id, t.team_long_name HAVING COUNT(*) = ( SELECT MAX(win_count) FROM ( SELECT COUNT(*) AS win_count FROM Match m2 JOIN League l2 ON m2.league`

**模型 SQL**：`SELECT T.team_long_name FROM Match AS M INNER JOIN Team AS T ON M.away_team_api_id = T.team_api_id INNER JOIN League AS L ON M.league_id = L.id WHERE L.name = 'Scotland Premier League' AND M.season = '2009/2010' AND M.away_team_goal > M.home_team_goal GROUP BY T.team_api_id, T.team_long_name ORDER BY COUNT(*) DESC LIMIT 1;`
### bird_1032  [MAX-subquery]  答错

**题面**：Give the name of the league with the highest matches of all time and how many matches were played in the said league.

**gold 返回 3 行**：`[['England Premier League', 3040], ['France Ligue 1', 3040], ['Spain LIGA BBVA', 3040]]`

**gold SQL**：`SELECT l.name, COUNT(m.id) AS match_count FROM League AS l JOIN Match AS m ON l.id = m.league_id GROUP BY l.id, l.name HAVING COUNT(m.id) = (SELECT MAX(match_count) FROM (SELECT COUNT(id) AS match_count FROM Match GROUP BY league_id ) )`

**模型 SQL**：`SELECT League.name, COUNT(Match.league_id) AS matches_played FROM Match JOIN League ON Match.league_id = League.id GROUP BY League.id, League.name ORDER BY COUNT(Match.league_id) DESC LIMIT 1`
### bird_1092  [MAX-subquery]  答错

**题面**：Give the names of the leagues with the most matches in the 2008/2009 season?

**gold 返回 4 行**：`[['England Premier League'], ['France Ligue 1'], ['Italy Serie A'], ['Spain LIGA BBVA']]`

**gold SQL**：`SELECT t1.name FROM League AS t1 JOIN Match AS t2 ON t1.id = t2.league_id WHERE t2.season = '2008/2009' GROUP BY t1.name HAVING COUNT(t2.id) = (SELECT MAX(match_count) FROM (SELECT COUNT(t2.id) AS match_count FROM Match AS t2 WHERE t2.season = '2008/2009' GROUP BY t2.league_id))`

**模型 SQL**：`SELECT League.name FROM Match JOIN League ON Match.league_id = League.id WHERE Match.season = '2008/2009' GROUP BY League.id, League.name ORDER BY COUNT(*) DESC LIMIT 1`
### bird_349  [MAX-subquery]  答错

**题面**：Name the card with the most ruling information and its artist. Also state if the card is a promotional printing.

**gold 返回 2 行**：`[["Teferi's Protection", 'Chase Stone', 0], ["Teferi's Protection", 'Chase Stone', 1]]`

**gold SQL**：`SELECT DISTINCT c.name, c.artist, c.isPromo FROM cards c INNER JOIN (SELECT uuid FROM rulings GROUP BY uuid HAVING COUNT(id) = ( SELECT MAX(ruling_count) FROM ( SELECT COUNT(id) as ruling_count FROM rulings GROUP BY uuid ) ) ) AS max_rulings ON c.uuid = max_rulings.uuid;`

**模型 SQL**：`SELECT cards.name, cards.artist, cards.isPromo FROM cards INNER JOIN rulings ON cards.uuid = rulings.uuid GROUP BY cards.uuid, cards.name, cards.artist, cards.isPromo ORDER BY COUNT(rulings.uuid) DESC LIMIT 1`
### bird_37  [MAX-subquery]  答错

**题面**：What is the complete address of the school with the lowest excellence rate? Indicate the Street, City, State, and Zip.

**gold 返回 17 行**：`[['2607 Myrtle Street', 'Oakland', 'CA', '94607-3415'], ['4521 Webster Street', 'Oakland', 'CA', '94609-2140'], ['2465 Dolan Way', 'San Pablo', 'CA', '94806-1668'], ['831 Chanslor Avenue', 'Richmond', 'CA', '94801-3533'], ['222 North Virgil Avenue', 'Los Angeles', 'CA', '90004-3622'], ['147 North Oc`

**gold SQL**：`SELECT s.Street, s.City, s.State, s.Zip FROM schools s JOIN satscores sat ON s.CDSCode = sat.cds WHERE sat.NumTstTakr > 0 AND sat.NumGE1500 IS NOT NULL AND sat.NumTstTakr IS NOT NULL AND rtype = 'S' AND CAST(sat.NumGE1500 AS FLOAT) / CAST(sat.NumTstTakr AS FLOAT) = (SELECT MIN(CAST(NumGE1500 AS FLOAT) / CAST(NumTstTakr AS FLOAT)) FROM satscores WHERE NumTstTakr > 0 AND NumGE1500 IS NOT NULL AND Nu`

**模型 SQL**：`SELECT T1.Street, T1.City, T1.State, T1.Zip FROM schools AS T1 INNER JOIN satscores AS T2 ON T2.cds = T1.CDSCode WHERE T2.NumTstTakr > 0 AND T2.NumGE1500 IS NOT NULL ORDER BY 1.0 * T2.NumGE1500 / T2.NumTstTakr ASC LIMIT 1`
### bird_736  [MAX-subquery]  答错

**题面**：Who is the dumbest superhero?

**gold 返回 3 行**：`[['Ammo'], ['Ando Masahashi'], ['Jack-Jack']]`

**gold SQL**：`SELECT s.superhero_name FROM superhero AS s JOIN hero_attribute AS ha ON s.id = ha.hero_id JOIN attribute AS a ON ha.attribute_id = a.id WHERE a.attribute_name = 'Intelligence' AND ha.attribute_value = ( SELECT MIN(attribute_value) FROM hero_attribute WHERE attribute_id = ( SELECT id FROM attribute WHERE attribute_name = 'Intelligence' ) )`

**模型 SQL**：`SELECT S.superhero_name FROM hero_attribute AS HA INNER JOIN attribute AS A ON HA.attribute_id = A.id INNER JOIN superhero AS S ON HA.hero_id = S.id WHERE A.attribute_name = 'Intelligence' ORDER BY HA.attribute_value ASC LIMIT 1`
### bird_794  [MAX-subquery]  答错

**题面**：Which hero was the fastest?

**gold 返回 40 行**：`[['Air-Walker'], ['Angela'], ['Ardina'], ['Aurora'], ['Ben 10'], ['Beyonder'], ['Binary'], ['Bizarro'], ['Black Bolt'], ['Black Flash'], ['Flash'], ['Flash II'], ['Flash III'], ['Flash IV'], ['General Zod'], ['Gladiator'], ['Hyperion'], ['Impulse'], ['Jack of Hearts'], ['Jesse Quick'], ['Kid Flash I`

**gold SQL**：`SELECT s.superhero_name FROM superhero AS s JOIN hero_attribute AS ha ON s.id = ha.hero_id JOIN attribute AS a ON ha.attribute_id = a.id WHERE a.attribute_name = 'Speed' AND ha.attribute_value = ( SELECT MAX(ha2.attribute_value) FROM hero_attribute AS ha2 JOIN attribute AS a2 ON ha2.attribute_id = a2.id WHERE a2.attribute_name = 'Speed' )`

**模型 SQL**：`SELECT superhero.superhero_name FROM superhero JOIN hero_attribute ON hero_attribute.hero_id = superhero.id JOIN attribute ON attribute.id = hero_attribute.attribute_id WHERE attribute.attribute_name = 'Speed' ORDER BY hero_attribute.attribute_value DESC LIMIT 1`
---

## 第二组（对照）：gold 只返回一行（LIMIT 1），随机抽 14 道

### bird_1479  [LIMIT1]  答对

**题面**：Which year recorded the most consumption of gas paid in CZK?

**gold 返回 1 行**：`[['2013']]`

**gold SQL**：`SELECT SUBSTR(T2.Date, 1, 4) FROM customers AS T1 INNER JOIN yearmonth AS T2 ON T1.CustomerID = T2.CustomerID WHERE T1.Currency = 'CZK' GROUP BY SUBSTR(T2.Date, 1, 4) ORDER BY SUM(T2.Consumption) DESC LIMIT 1`

**模型 SQL**：`SELECT SUBSTR(T1.Date, 1, 4) AS Year FROM yearmonth AS T1 INNER JOIN customers AS T2 ON T1.CustomerID = T2.CustomerID WHERE T2.Currency = 'CZK' GROUP BY SUBSTR(T1.Date, 1, 4) ORDER BY SUM(T1.Consumption) DESC LIMIT 1`
### bird_1146  [LIMIT1]  答对

**题面**：Please provide the full name of the away team that scored the most goals in one match.

**gold 返回 1 行**：`[['Paris Saint-Germain']]`

**gold SQL**：`SELECT t2.team_long_name FROM Match AS t1 INNER JOIN Team AS t2 ON t1.away_team_api_id = t2.team_api_id ORDER BY t1.away_team_goal DESC LIMIT 1`

**模型 SQL**：`SELECT T2.team_long_name FROM Match AS T1 INNER JOIN Team AS T2 ON T1.away_team_api_id = T2.team_api_id ORDER BY T1.away_team_goal DESC LIMIT 1;`
### bird_208  [LIMIT1]  答对

**题面**：Which type of label is the most numerous in molecules with hydrogen?

**gold 返回 1 行**：`[['-']]`

**gold SQL**：`SELECT T.label FROM ( SELECT T2.label, COUNT(T2.molecule_id) FROM atom AS T1 INNER JOIN molecule AS T2 ON T1.molecule_id = T2.molecule_id WHERE T1.element = 'h' GROUP BY T2.label ORDER BY COUNT(T2.molecule_id) DESC LIMIT 1 ) t`

**模型 SQL**：`SELECT m.label FROM molecule AS m JOIN atom AS a ON m.molecule_id = a.molecule_id WHERE a.element = 'h' GROUP BY m.label ORDER BY COUNT(DISTINCT m.molecule_id) DESC LIMIT 1`
### bird_892  [LIMIT1]  答对

**题面**：State the driver with the most points scored. Find his full name and the number of points.

**gold 返回 1 行**：`[['Lewis', 'Hamilton', 2382.0]]`

**gold SQL**：`SELECT d.`forename`, d.`surname`, SUM(r.`points`) AS total_points FROM `results` r JOIN `drivers` d ON d.`driverId` = r.`driverId` GROUP BY r.`driverId` ORDER BY total_points DESC LIMIT 1;`

**模型 SQL**：`SELECT d.forename, d.surname, SUM(r.points) AS points FROM results AS r INNER JOIN drivers AS d ON r.driverId = d.driverId GROUP BY d.driverId, d.forename, d.surname ORDER BY SUM(r.points) DESC LIMIT 1`
### bird_1030  [LIMIT1]  答对

**题面**：Give the name of the league had the most matches end as draw in the 2016 season?

**gold 返回 1 行**：`[['France Ligue 1']]`

**gold SQL**：`SELECT t2.name FROM Match AS t1 INNER JOIN League AS t2 ON t1.league_id = t2.id WHERE t1.season = '2015/2016' AND t1.home_team_goal = t1.away_team_goal GROUP BY t2.name ORDER BY COUNT(t1.id) DESC LIMIT 1`

**模型 SQL**：`SELECT name FROM League WHERE id = ( SELECT league_id FROM Match WHERE season = '2015/2016' GROUP BY league_id ORDER BY SUM(home_team_goal = away_team_goal) DESC LIMIT 1 )`
### bird_1079  [LIMIT1]  答对

**题面**：Which player is the tallest?

**gold 返回 1 行**：`[['Kristof van Hout']]`

**gold SQL**：`SELECT player_name FROM Player ORDER BY height DESC LIMIT 1`

**模型 SQL**：`SELECT player_name FROM Player ORDER BY height DESC LIMIT 1`
### bird_732  [LIMIT1]  答对

**题面**：Which publisher published the slowest superhero?

**gold 返回 1 行**：`[['Marvel Comics']]`

**gold SQL**：`SELECT T2.publisher_name FROM superhero AS T1 INNER JOIN publisher AS T2 ON T1.publisher_id = T2.id INNER JOIN hero_attribute AS T3 ON T1.id = T3.hero_id INNER JOIN attribute AS T4 ON T3.attribute_id = T4.id WHERE T4.attribute_name = 'Speed' ORDER BY T3.attribute_value LIMIT 1`

**模型 SQL**：`SELECT P.publisher_name FROM superhero AS S INNER JOIN hero_attribute AS HA ON S.id = HA.hero_id INNER JOIN attribute AS A ON HA.attribute_id = A.id INNER JOIN publisher AS P ON S.publisher_id = P.id WHERE A.attribute_name = 'Speed' ORDER BY HA.attribute_value ASC LIMIT 1`
### bird_1098  [LIMIT1]  答对

**题面**：What is Ajax's highest chance creation passing score and what is it classified as?

**gold 返回 1 行**：`[[67, 'Risky']]`

**gold SQL**：`SELECT t2.chanceCreationPassing, t2.chanceCreationPassingClass FROM Team AS t1 INNER JOIN Team_Attributes AS t2 ON t1.team_api_id = t2.team_api_id WHERE t1.team_long_name = 'Ajax' ORDER BY t2.chanceCreationPassing DESC LIMIT 1`

**模型 SQL**：`SELECT TA.chanceCreationPassing, TA.chanceCreationPassingClass FROM Team AS T JOIN Team_Attributes AS TA ON T.team_api_id = TA.team_api_id WHERE T.team_long_name = 'Ajax' ORDER BY TA.chanceCreationPassing DESC LIMIT 1`
### bird_189  [LIMIT1]  答对

**题面**：Name the account number of the oldest female client, with ties broken by the client’s district average salary in ascending order.

**gold 返回 1 行**：`[[1743]]`

**gold SQL**：`SELECT T3.account_id FROM client AS T1 INNER JOIN district AS T2 ON T1.district_id = T2.district_id INNER JOIN account AS T3 ON T2.district_id = T3.district_id INNER JOIN disp AS T4 ON T1.client_id = T4.client_id AND T4.account_id = T3.account_id WHERE T1.gender = 'F' ORDER BY T1.birth_date ASC, T2.A11 ASC LIMIT 1`

**模型 SQL**：`SELECT account.account_id FROM client JOIN disp ON client.client_id = disp.client_id JOIN account ON disp.account_id = account.account_id JOIN district ON client.district_id = district.district_id WHERE client.gender = 'F' ORDER BY client.birth_date ASC, district.A11 ASC LIMIT 1`
### bird_82  [LIMIT1]  答对

**题面**：What is the grade span offered in the school with the highest longitude?

**gold 返回 1 行**：`[['K-8']]`

**gold SQL**：`SELECT GSoffered FROM schools WHERE school is not null ORDER BY ABS(longitude) DESC LIMIT 1`

**模型 SQL**：`SELECT GSoffered FROM schools WHERE Longitude IS NOT NULL ORDER BY ABS(Longitude) DESC LIMIT 1;`
### bird_931  [LIMIT1]  答对

**题面**：What was the fastest lap speed among all drivers in the 2009 Spanish Grand Prix?

**gold 返回 1 行**：`[['202.484']]`

**gold SQL**：`SELECT T2.fastestLapSpeed FROM races AS T1 INNER JOIN results AS T2 ON T2.raceId = T1.raceId WHERE T1.name = 'Spanish Grand Prix' AND T1.year = 2009 AND T2.fastestLapSpeed IS NOT NULL ORDER BY T2.fastestLapSpeed DESC LIMIT 1`

**模型 SQL**：`SELECT results.fastestLapSpeed FROM results INNER JOIN races ON results.raceId = races.raceId WHERE races.name = 'Spanish Grand Prix' AND races.year = 2009 AND results.fastestLapSpeed IS NOT NULL ORDER BY CAST(results.fastestLapSpeed AS REAL) DESC LIMIT 1;`
### bird_687  [LIMIT1]  答对

**题面**：How many comments were added to the post with the highest score?

**gold 返回 1 行**：`[[3]]`

**gold SQL**：`SELECT COUNT(T2.Id) FROM posts AS T1 INNER JOIN comments AS T2 ON T1.Id = T2.PostId GROUP BY T1.Id ORDER BY T1.Score DESC LIMIT 1`

**模型 SQL**：`SELECT CommentCount FROM posts ORDER BY Score DESC LIMIT 1`
### bird_1238  [LIMIT1]  答对

**题面**：Among the patients who were diagnosed with SLE, who is the oldest with normal hemoglobin level. Provide the ID and sex.

**gold 返回 1 行**：`[[4792723, 'F']]`

**gold SQL**：`SELECT T1.ID, T1.SEX FROM Patient AS T1 INNER JOIN Laboratory AS T2 ON T1.ID = T2.ID WHERE T1.Diagnosis = 'SLE' AND T2.HGB > 10 AND T2.HGB < 17 ORDER BY T1.Birthday ASC LIMIT 1`

**模型 SQL**：`SELECT P.ID, P.SEX FROM Patient AS P INNER JOIN Laboratory AS L ON P.ID = L.ID WHERE P.Diagnosis = 'SLE' AND L.HGB > 10 AND L.HGB < 17 ORDER BY P.Birthday ASC, P.ID ASC LIMIT 1`
### bird_1025  [LIMIT1]  答对

**题面**：Give the name of the league had the most goals in the 2016 season?

**gold 返回 1 行**：`[['Spain LIGA BBVA']]`

**gold SQL**：`SELECT t2.name FROM Match AS t1 INNER JOIN League AS t2 ON t1.league_id = t2.id WHERE t1.season = '2015/2016' GROUP BY t2.name ORDER BY SUM(t1.home_team_goal + t1.away_team_goal) DESC LIMIT 1`

**模型 SQL**：`SELECT L.name FROM Match AS M JOIN League AS L ON M.league_id = L.id WHERE M.season = '2015/2016' GROUP BY L.id, L.name ORDER BY SUM(M.home_team_goal + M.away_team_goal) DESC LIMIT 1`