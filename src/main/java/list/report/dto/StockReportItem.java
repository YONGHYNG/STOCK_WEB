package list.report.dto;

public class StockReportItem {
    private String stockName;
    private String title;
    private String date;

    public StockReportItem(String stockName, String title, String date) {
        this.stockName = stockName;
        this.title = title;
        this.date = date;
    }

    public String getStockName(){
        return stockName;
    }

    public String getTitle(){
        return title;
    }

    public String getDate(){
        return date;
    }
}
