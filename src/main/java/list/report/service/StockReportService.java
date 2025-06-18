package list.report.service;

import list.report.dto.StockReportItem;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class StockReportService {

    public List<StockReportItem> fetchStockReports() {
        List<StockReportItem> result = new ArrayList<>();

        try {
            String url = "https://finance.naver.com/research/company_list.naver";
            Document doc = Jsoup.connect(url).userAgent("Mozilla/5.0").get();

            Elements rows = doc.select("table.type_1 tbody tr");
            int count = 0;

            for(Element row : rows){
                Elements tds = row.select("td");
                if(tds.size() < 6) continue;

                String stockName = tds.get(0).text().trim();
                String title = tds.get(1).text().trim();
                String date = tds.get(5).text().trim();

                result.add(new StockReportItem(stockName, title, date));
                count++;

                if(count >=10) break;
            }
        } catch (IOException e) {
             e.printStackTrace();
        }

        return result;
    }

}
