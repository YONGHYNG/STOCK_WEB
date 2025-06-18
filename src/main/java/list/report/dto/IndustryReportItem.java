package list.report.dto;

public class IndustryReportItem {
    private String title;
    private String company;
    private String date;

    public IndustryReportItem(String title, String company, String date){
        this.title = title;
        this.company = company;
        this.date = date;
    }

    public String getTitle(){
        return title;
    }

    public String getCompany(){
        return company;
    }

    public String getDate(){
        return date;
    }
}
