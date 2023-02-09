структура модуля стратегия

на вход подаются свечки с закрывающими ценами и наличие позиции

на выходе дают команду WAIT,BUY,SELL и цену 


 variants:
 
in position:
 wait or sell 

not in position:
 wait or buy

graph TD
    A[Enter Chart Definition] --> B(Preview)
    B --> C{decide}
    C --> D[Keep]
    C --> E[Edit Definition]
    E --> B
    D --> F[Save Image and Code]
    F --> B


