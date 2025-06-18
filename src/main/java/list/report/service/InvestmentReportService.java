package list.report.service;

import list.report.dto.InvestmentReportItem;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.List;

@Service
public class InvestmentReportService {

    public List<InvestmentReportItem> fetchInvestmentReports() {
        List<InvestmentReportItem> result = new ArrayList<>();

        try {
            String url = "https://finance.naver.com/research/invest_list.naver";
            Document doc = Jsoup.connect(url).userAgent("Mozilla/5.0").get();

            Elements rows = doc.select("table.type_1 tr");

            for(Element row : rows) {
                Elements tds = row.select("td");
                if(tds.size() < 2) continue;

                String title = tds.get(0).text().trim();
                String company = tds.get(1).text().trim();

                result.add(new InvestmentReportItem(company, title));

                if (result.size() >=10) break;
            }
        } catch (Exception e) {
            e.printStackTrace();
        }

        return result;
    }
}
