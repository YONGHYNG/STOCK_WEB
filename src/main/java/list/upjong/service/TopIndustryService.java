package list.upjong.service;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.select.Elements;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

@Service
public class TopIndustryService {

    public List<String> getTop5Industries() throws IOException {
        String url = "https://finance.naver.com/sise/sise_group.naver?type=upjong";
        Document doc = Jsoup.connect(url).get();

        Elements rows = doc.select("table.type_1 tr");
        List<String> top5 = new ArrayList<>();

        for (Element row : rows) {
            Elements cols = row.select("td");

            if (cols.size() > 4) { // 필터링: 데이터가 있는 tr만 선택
                String name = cols.get(0).text();
                String change = cols.get(2).text();

                top5.add(name + " (" + change + ")");

                if (top5.size() == 5) break;
            }
        }

        return top5;
    }
}

