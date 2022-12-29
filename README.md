https://www.dataquest.io/blog/python-datetime-tutorial/


Process

check open deal and in_position flag
1) if it is then get order_id
check the sell conditions: momentum > 70 
   
2)if it isn't then try to get deal from the db
if it is then in_position = true and go to 1)
if it isn't then check buy conditions

buy, save order id into db and in_position = true



