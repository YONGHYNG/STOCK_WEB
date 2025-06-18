package list.report.service;

import list.report.dto.IndustryReportItem;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class IndustryService {

    public List<IndustryReportItem> fetchIndustryReport() {
        List<IndustryReportItem> reportList = new ArrayList<>();

    try {
        String url = "https://finance.naver.com/research/industry_list.naver";
        Document doc = Jsoup.connect(url).userAgent("Mozilla/5.0").get();

        Elements rows = doc.select("table.type_1 tr");

        int count = 0;
        for(Element row : rows) {
            Elements tds = row.select("td");
            if(tds.size() < 5) continue;

            String title = tds.get(0).text().trim();
            String company = tds.get(1).text().trim();
            String date = tds.get(5).text().trim();

            reportList.add(new IndustryReportItem(company, title, date));
            count++;

            if(count >=10) break;
        }
    } catch (IOException e) {
        e.printStackTrace();
    }

    return reportList;
    }

}
