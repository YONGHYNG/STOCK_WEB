package list.report.dto;

public class InvestmentReportItem {

    private String company;
    private String title;

    public InvestmentReportItem(String company, String title){
        this.company = company;
        this.title = title;
    }

    public String getCompany(){
        return company;
    }

    public String getTitle(){
        return title;
    }
}
